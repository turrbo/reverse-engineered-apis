# Explore.org Wildlife Camera API — Reverse-Engineering Notes

**Reverse-engineered:** March 2026
**Site:** https://explore.org/livecams
**Client file:** `explore_org_client.py`

---

## Overview

Explore.org operates a live wildlife and nature camera network with 232 cameras across Africa, Alaska, the oceans, bird nests, animal sanctuaries, and more.  The site is a React/Redux SPA that consumes a set of JSON REST endpoints and a Cloudfront streaming CDN.  **All read endpoints are public and require no authentication.**

---

## Discovered Endpoints

### 1. REST API — Camera Metadata

Both hostnames serve identical data.  `explore.org` is the public-facing mirror; `omega.explore.org` is the internal hostname referenced in the JS bundle.

#### List all cameras
```
GET https://explore.org/api/livecams
GET https://omega.explore.org/api/livecams
```
Returns 232 camera objects.  No query parameters are honoured (always returns full list).

**Response:**
```json
{
  "status": "success",
  "message": "Received livecams.",
  "data": {
    "livecams": [ { ...camera... }, ... ]
  }
}
```

**Camera object fields:**

| Field | Type | Notes |
|-------|------|-------|
| `id` | int | Numeric camera id |
| `uuid` | string | UUID v4 |
| `active` | bool | Whether listed on site |
| `title` | string | Display name |
| `slug` | string | URL slug |
| `offline_label` | string | "Off Season", "Highlights", "Film", etc. |
| `primary_channel_id` | int | Top-level channel id |
| `primary_cam_group_id` | int | Camera group id |
| `location_id` | int | Geographic location id |
| `date_live` | ISO8601 | When the camera went live |
| `meta_description` | string | SEO description |
| `description` | string | HTML description |
| `thumbnail_large_url` | string | Thumbnail image |
| `stillframe` | object | Responsive image set (498/853/1280/1920 px wide) |
| `is_featured` | bool | Featured on homepage |
| `partner_id` | int | Partner organisation id |
| `best_viewing_start_time` | "HH:MM:SS" | Prime viewing window start |
| `best_viewing_end_time` | "HH:MM:SS" | Prime viewing window end |
| `prime_all_day` | bool | Active all day |
| `prime_all_night` | bool | Active all night |
| `is_meditation` | bool | Is a meditation/ambient cam |
| `snapshot_enabled` | bool | Snapshots can be taken |
| `is_offline` | bool | Currently offline/off-season |
| `recordings_template` | string | e.g. `EXP-STMSurface` — used to build HLS/snapshot URLs |
| `wowza_fqdn` | string | Wowza server FQDN (informational; actual streams served from Cloudfront) |
| `recording_priority` | int/null | Internal encoding priority |
| `twitter_text` / `pinterest_text` / `facebook_text` | string | Pre-written social share text |
| `legacy_id` | int/null | Old numeric id |

---

#### List camera groups
```
GET https://explore.org/api/camgroups
GET https://omega.explore.org/api/camgroups
```
Returns 108 camera groups (sub-categories / partnerships).

**Group object fields:** `id, uuid, active, title, slug, image_url, poster_url, poster { image_set { width, height } }, multi_livecam, location_text`

**Selected groups:**

| id | slug | title |
|----|------|-------|
| 1 | national-audubon-society | National Audubon Society |
| 2 | african-wildlife | African Wildlife |
| 5 | decorah-eagles | Decorah Eagles (RRP) |
| 6 | decorah-north-eagles | Decorah North Eagles |
| 20 | brown-bears | Brown Bears (Katmai) |
| 21 | brooks-falls-bears | Brooks Falls Bears |
| 22 | brooks-falls-underwater | Brooks Falls Underwater |
| 23 | kitten-rescue | Kitten Rescue |
| 27 | warrior-canine-connection | Warrior Canine Connection |
| 43 | monterey-bay-aquarium | Monterey Bay Aquarium |
| 75 | polar-bears-international | Polar Bears International |
| 95 | bears | All Bears (combined) |
| 122 | blue-spring-manatees | Blue Spring State Park (Manatees) |

---

#### List navigation channels
```
GET https://explore.org/api/channels
GET https://omega.explore.org/api/channels
```

Returns 11 top-level navigation channels with their associated cam_group id lists.

| id | title | cam_groups |
|----|-------|-----------|
| 16 | Featured | [79, 5, 12, 148, 140, 141, 122, 76, 6, 43, 27, 23, 50] |
| 1 | Africa | [118, 140, 2, 100, 119] |
| 5 | Bears | [95, 75, 20, 139, 21, 22] |
| 4 | Birds | [6, 144, 152, 151, 15, 130, 148, 72, 5, ...] |
| 10 | Oceans | [43, 44, 37, 129, 122, 41, 40, 35, 36, ...] |
| 8 | Dog Bless You | [27, 143, 33, 30, 34, 109] |
| 7 | Cat Rescues | [23, 137, 24] |
| 18 | Sanctuaries | [96, 128, 93, 58] |
| 13 | Zen Cams | [50, 153, 73, 76, 19, 49, ...] |
| 20 | All Cams | [63] |
| 21 | Multi-View | [141, 149, 147, 146, 145, 142] |

---

#### Get feeds for a camera group
```
GET https://omega.explore.org/api/get_cam_group_snapshots.json?t={unix_ts}&id={group_id}
```

This is the richest endpoint — it returns live feed data including `stream_id`, current snapshot URL, `current_viewers`, and `is_offline` status.  Used by the web player to populate the sidebar.

**Parameters:**
- `id` — cam group id (required)
- `t` — Unix timestamp for cache-busting (use 0 for latest)

**Feed object fields** (in addition to camera fields):

| Field | Type | Notes |
|-------|------|-------|
| `stream_id` | string | Numeric stream id (as string) — use with streams CDN |
| `snapshot` | string | Latest snapshot URL from snapshots.explore.org |
| `current_viewers` | int | Real-time viewer count |
| `is_inactive` | bool | Seasonal inactivity |
| `force_offline` | bool | Manually forced offline |
| `blurred_snapshot_url` | string | Blurred background version |
| `is_film` | bool | Film content (not live) |
| `cam_group` | object | `{ id }` |
| `order` | int | Display order in group |
| `timestamp` | int | Snapshot Unix timestamp |

---

#### Search
```
GET https://omega.explore.org/api/search_results.json?q={query}
```

Full-text search across cameras, groups, and content.

**Response:**
```json
{
  "status": "success",
  "data": {
    "feeds": [ { ...feed... }, ... ]
  }
}
```

---

#### Events / schedule
```
GET https://omega.explore.org/api/events
```

Returns 1 000+ scheduled events (live shows, guided tours, special broadcasts).

**Event fields:** `id, event_id, is_canceled, summary, description, start_time, end_time, created_at, updated_at, is_all_day`

---

#### User snapshots (community photos)
```
GET https://omega.explore.org/api/snapshots/all
    ?per_page={N}
    &cursor={base64_cursor}
    &livecam_id={id}
    &cam_group_id={id}
```

Cursor-paginated list of user-submitted snapshot photos.

**Snapshot fields:** `title, caption, thumbnail, snapshot, num_favorites, username, user_id, uuid, display_name, avatar_uri, timezone, timestamp, local_time, created_at, livecam_id, youtube_id, youtube_delta`

---

### 2. Streaming CDN — HLS Streams

```
GET https://d11gsgd2hj8qxd.cloudfront.net/streams.json
GET https://d11gsgd2hj8qxd.cloudfront.net/streams.json?q[id_in][]=216&q[id_in][]=215
```

Returns real-time stream status for all 145 streams (or a subset when id filters provided).

**Stream object:**
```json
{
  "id": 216,
  "name": "Decorah Eagles - Fish Hatchery",
  "playlistUrl": "https://outbound-production.explore.org/stream-production-216/.m3u8",
  "snapshotHost": "snapshots-production.explore.org",
  "placeholderUrl": "",
  "currentTime": "2026-03-27T12:28:09-05:00",
  "state": "live",
  "numberOfViewers": 546
}
```

**HLS playlist URL pattern (no auth required):**
```
https://outbound-production.explore.org/stream-production-{stream_id}/.m3u8
```

Stream states:
- `live` — camera is actively streaming (126 of 145 at time of research)
- `on_demand` — playing looped/recorded content (19 of 145)

---

### 3. Snapshot Images

#### Latest live snapshot
```
https://snapshots.explore.org/{template}-EDGE/{template}-EDGE-{unix_ts}.jpg
https://snapshots.explore.org/{template}-EDGE/{template}-EDGE-{unix_ts}-scaled.jpg
```

Where `{template}` is the camera's `recordings_template` field (e.g. `EXP-FallsLow`).  The timestamp is the Unix epoch of the HLS segment.  The `-scaled` variant is a smaller resolution version.

Example:
```
https://snapshots.explore.org/EXP-BrownBearsMeditation-EDGE/EXP-BrownBearsMeditation-EDGE-1774632406-scaled.jpg
```

The current snapshot URL is served directly in the feed data from `/api/get_cam_group_snapshots.json`.

#### User-submitted snapshots
```
https://files.explore.org/sn/{year}/{month}/{day}/{filename}.jpg
```

---

### 4. WebSocket — Live Snapshot Feed

```
wss://snapdata.prod.explore.org/oldest/{template}-EDGE
```

Receives real-time snapshot events as new HLS segments are available.  Used by the web player to update the snapshot timeline.

---

### 5. Media CDN

All camera images are served from:

```
https://media.explore.org/stillframes/{filename}__media_{W}x{H}.jpg
https://media.explore.org/posters/{filename}__media_{W}x{H}.jpg
https://media.explore.org/blurred-snapshots/{slug}_blurred.jpg
```

Available stillframe widths: `498, 853, 1280, 1920` (px)
Available poster widths: `200, 320, 480, 720` (px)

---

### 6. Comments / GraphQL

```
POST https://comments.explore.org/graphql
```

Requires a `query` or `queryId` field in the JSON body.  Not reverse-engineered further; requires user JWT from `omega.explore.org/auth`.

---

### 7. Authentication (optional)

```
POST https://omega.explore.org/api/api/v1/accounts/login/
POST https://omega.explore.org/api/api/v1/getdata/   (Bearer token)
```

OAuth social login:
```
https://omega.explore.org/auth/google?...
https://omega.explore.org/auth/apple?...
https://omega.explore.org/auth/facebook?...
https://omega.explore.org/auth/twitter?...
```

Authentication is only required for:
- Submitting snapshots
- Rating snapshots
- Toggling snapshot favorites
- Accessing user profile data
- The `cameraToken` used to authorise the streams CDN (only for certain features; the public streams.json endpoint works without it)

---

## Client Usage

### Installation
```bash
pip install requests
```

### Quick start
```python
from explore_org_client import ExploreOrgClient

client = ExploreOrgClient()

# Summary statistics
print(client.camera_summary())

# List all cameras
cameras = client.list_cameras()

# Active cameras only
active = client.list_active_cameras()

# Bear cameras
bears = client.get_cameras_by_channel('Bears')

# Get stream URL for Decorah Eagles (stream_id=216)
url = client.get_stream_url(216)
# https://outbound-production.explore.org/stream-production-216/.m3u8

# Get all live streams with viewer counts
live = client.list_live_streams()

# Most watched
top = client.most_watched(top_n=10)

# Search
results = client.search('polar bear')

# Get feeds for a camera group (includes stream_id, snapshot URL, viewer count)
feeds = client.get_camgroup_feeds(group_id=20)  # Brown Bears

# User snapshots (paginated)
page = client.list_snapshots(per_page=20)
for snap in page['data']:
    print(snap['title'], snap['snapshot'])

# Events / schedule
events = client.list_upcoming_events()

# Build snapshot URL from recordings_template
snap_url = client.build_snapshot_url('EXP-FallsLow', unix_timestamp=1774632406)
```

### Play a stream with ffplay
```bash
ffplay "https://outbound-production.explore.org/stream-production-216/.m3u8"
```

### Play a stream with VLC
```bash
vlc "https://outbound-production.explore.org/stream-production-216/.m3u8"
```

---

## Data Relationships

```
Channel (11)
  └── cam_groups[] (108 total)
        └── feeds / cameras (232 total)
              ├── recordings_template  →  HLS m3u8 URL
              ├── stream_id            →  streams.json CDN
              └── snapshot             →  snapshots.explore.org
```

---

## Known API Limitations

1. **No single-camera detail endpoint** — `/api/livecams/{id}` returns empty HTML (200 OK, empty body).  Use list_cameras() and filter client-side.
2. **No direct camgroup detail endpoint** — `/api/camgroups/{id}` returns 404.  Use list_camgroups() and filter.
3. **streams.json filter bug** — `?q[id_in][]=53` does not return stream id 53; it appears to do a modular/hash lookup and may return other streams.  Use list_streams() and filter client-side.
4. **Wowza FQDN** — The `wowza_fqdn` field (e.g. `wowza1-us-central-1-prod.explore.org`) is no longer publicly resolvable.  All HLS delivery has migrated to the `outbound-production.explore.org` CDN.
5. **Snapshot timestamps** — The timestamp embedded in snapshot URLs changes every ~10 seconds (one HLS segment).  Use the `snapshot` URL from get_camgroup_feeds() for the most recent image rather than guessing timestamps.
6. **Search is omega-only** — `search_results.json` is only on omega.explore.org, not on explore.org/api.

---

## Rate Limiting

No rate limiting was observed during research.  The API does not require an API key for read operations.  Be respectful: the streams CDN serves live video to thousands of concurrent viewers; do not hit it in tight loops.
