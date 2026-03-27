# Explore.org Live Camera API – Reverse Engineering Report

**Site:** https://explore.org/livecams  
**API Base:** `https://omega.explore.org/api`  
**Documented:** 2026-03-27  
**Cameras found:** 232 (127 live, 105 offline/seasonal)

---

## Overview

Explore.org hosts 232 nature and wildlife live cameras organized into 15 content channels (Africa, Bears, Birds, Oceans, etc.). The site is a React SPA backed by a REST API at `https://omega.explore.org/api`. All video content is delivered via embedded YouTube live streams.

The API was reverse-engineered by analyzing the compiled JS bundle (`/dist/app.js`) and observing network requests.

---

## Camera Statistics (as of 2026-03-27)

| Channel | Total | Live | Offline |
|---------|-------|------|---------|
| Africa | 20 | 14 | 6 |
| Bears | 20 | 1 | 19 |
| Birds | 65 | 49 | 16 |
| Bison | 2 | 2 | 0 |
| Cat Rescues | 7 | 7 | 0 |
| Curators | 18 | 0 | 18 |
| Dog Bless You | 16 | 5 | 11 |
| Farm Sanctuary | 7 | 4 | 3 |
| Grasslands | 4 | 3 | 1 |
| Nature Films | 4 | 2 | 2 |
| Oceans | 43 | 22 | 21 |
| Pollinators | 4 | 4 | 0 |
| Sanctuaries | 3 | 3 | 0 |
| Zen Cams | 18 | 11 | 7 |
| **Total** | **232** | **127** | **105** |

> Most "offline" cameras are seasonal (e.g. Katmai bears, panda breeding centers). They retain their YouTube IDs and can be watched as archived streams.

---

## Architecture

```
explore.org (React SPA)
    └── omega.explore.org/api  (REST JSON API)
            ├── /initial         ← channel+camgroup index on page load
            ├── /get_livecam_info.json?id=<id>  ← individual camera details
            ├── /get_cam_group_info.json?id=<id> ← cam-group with all feeds
            └── ...
```

All video streams are YouTube embeds: `https://www.youtube.com/embed/<VIDEO_ID>?autoplay=1`.

---

## API Endpoints

### Public (No Auth Required)

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/initial` | **Primary endpoint.** Returns channels, cam-groups, default camera, website config. Called on every page load. |
| GET | `/channels` | Channel (category) list with cam-group IDs |
| GET | `/get_livecam_info.json?id=<id>` | Full camera metadata: title, slug, description, YouTube ID, partner, location, viewer count, weather |
| GET | `/get_cam_group_info.json?id=<id>&t=<ts>` | Cam-group with all feed metadata |
| GET | `/get_cam_group_snapshots.json?id=<id>&t=<ts>` | Snapshot thumbnails for all feeds in a cam-group |
| GET | `/get_page.json?page=<path>` | CMS page data for any URL path |
| GET | `/landing-pages/active` | Landing page block data |
| GET | `/get_homepage_alert` | Active alert banners |
| GET | `/events` | Calendar events (1000+) |
| GET | `/search_results.json?q=<query>` | Search cameras, blogs, videos, users |
| GET | `/snapshots/all?page=<n>&first=<n>` | Paginated recent user snapshots |
| GET | `/snapshots/livecam?livecam_id=<id>&page=<n>&first=<n>` | Camera snapshots |
| GET | `/snapshots/channel?channel_id=<id>&page=<n>&first=<n>` | Channel snapshots |
| GET | `/snapshots/gallery/<slug>` | Gallery snapshots |
| GET | `/snapshots/galleries` | Gallery/contest listings |
| GET | `/snapshots/contest-info/<id>` | Contest details |
| GET | `/snapshots/gallery-info/<slug>` | Gallery details |
| GET | `/snapshots/single?<params>` | Single snapshot lookup |
| POST | `/get_metadata.json` body: `{"path": "/livecams/bald-eagles/..."}` | SEO metadata for a page |
| GET | `/get_user_info.json?username=<u>` | Public user profile |
| GET | `/get_grants` | Grant/funding information |
| GET | `/get_faqs` | FAQ content |
| GET | `/get_films` | Films listing |
| GET | `/testimonials` | Testimonials |
| GET | `/get_galleries` | Photo galleries |
| GET | `/cameras/token` | Pusher token (live viewer count WebSocket) |
| GET | `/get_tutorial_videos` | Tutorial videos |
| GET | `/get_gallery_by_slug?gallery=<slug>` | Gallery by slug |
| GET | `/ping` | Health check |
| GET | `/redirects` | URL redirect map |

### Authenticated (Bearer Token Required)

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/auth/login` | `{email, password}` → JWT token |
| POST | `/auth/logout` | Invalidate token |
| POST | `/auth/register` | Create account |
| POST | `/auth/forgot_password` | Password reset email |
| POST | `/auth/reset_password` | Complete reset |
| GET | `/auth/get_authenticated_user_info` | Current user info |
| POST | `/auth/newsletter_subscribe` | Newsletter opt-in |
| POST | `/auth/associate` | Associate social login |
| POST | `/accounts/edit_profile` | Update profile |
| POST | `/accounts/save_avatar` | Upload avatar |
| POST | `/accounts/upload_avatar` | Upload avatar image |
| POST | `/accounts/save_user_preferences` | Save UI preferences |
| POST | `/accounts/password` | Change password |
| GET | `/get_user_favorites.json?id=<id>` | User's favorite cameras |
| POST | `/add_favorite` | Add camera to favorites |
| POST | `/remove_favorite` | Remove camera from favorites |
| POST | `/live-cams/create_snapshot` | Create snapshot |
| POST | `/broadcast/facebook` | Facebook broadcast |
| GET | `/broadcast/templates?id=<id>` | Broadcast templates |
| POST | `/broadcast/player-alert` | Player alert |

### GraphQL (Comments System)

Comments use a separate GraphQL API at `https://comments-api.dev.explore.org/graphql`.

Key queries: `board`, `allComments`, `latestComments`, `boardsForLivecams`  
Key mutations: `submitComment`, `addReaction`, `removeReaction`

---

## Data Models

### Camera (`/get_livecam_info.json`)

```json
{
  "id": 199,
  "title": "Decorah Eagles",
  "slug": "decorah-eagles",
  "uuid": "8f88f967-f93a-45c5-a303-7aa5229e45ec",
  "video_id": "IVmL3diwJuw",
  "large_feed_html": "https://www.youtube.com/embed/IVmL3diwJuw?rel=0&showinfo=0&autoplay=1&playsinline=1",
  "stream_id": "216",
  "location_text": "Decorah, Iowa, USA",
  "first_location": "Decorah Fish Hatchery",
  "description": "<p>HTML description...</p>",
  "tags": "eagle, birds, nest, decorah, bald eagles, iowa, raptor, live",
  "channel": {"id": 4, "title": "Birds", "blog_channel": "Bird-Cams", "slug": ""},
  "cam_group": {"id": 5, "title": "Bald Eagles", "slug": "bald-eagles", ...},
  "camgroup_slug": "bald-eagles",
  "partner": {"id": 24, "title": "Raptor Resource Project", "website": "...", ...},
  "is_offline": false,
  "force_offline": false,
  "is_offseason": false,
  "canonical_url": "https://explore.org/livecams/bald-eagles/decorah-eagles",
  "latlong": ["43.275813", "-91.779292"],
  "thumbnail_large_url": "https://files.explore.org/...",
  "best_viewing_start_time": "00:00:00",
  "best_viewing_end_time": "00:00:00",
  "current_viewers": 544,
  "primary_canonical_cam_group_slug": "bald-eagles",
  "weather": { "current": { "tempF": 37, "windSpeed": 16, ... }, "forecast": [...] },
  "facts": [],
  "alerts": [...]
}
```

### /initial Response Structure

```json
{
  "status": "success",
  "data": {
    "channels": [
      {"id": 4, "title": "Birds", "cam_groups": [6, 144, 152, ...], "order": 0}
    ],
    "camgroups": [
      {
        "id": 5, "title": "Bald Eagles", "slug": "bald-eagles",
        "feed_count": 11, "multi_livecam": false,
        "feeds": [
          {"id": 199, "title": "Decorah Eagles", "slug": "decorah-eagles", "uuid": "..."}
        ]
      }
    ],
    "default_livecam": { /* full camera object */ },
    "channels": [...],
    "website_backgrounds": [...],
    "countries": [...],
    "alerts": [...],
    "snapshotsEnabled": true
  }
}
```

---

## URL Patterns

```
# Camera page
https://explore.org/livecams/<cam-group-slug>/<camera-slug>
# Example:
https://explore.org/livecams/bald-eagles/decorah-eagles

# Cam-group page  
https://explore.org/livecams/<cam-group-slug>
# Example:
https://explore.org/livecams/brown-bears

# YouTube embed
https://www.youtube.com/embed/<VIDEO_ID>?rel=0&showinfo=0&autoplay=1&playsinline=1

# YouTube watch
https://www.youtube.com/watch?v=<VIDEO_ID>

# Still frame / snapshot
https://media.explore.org/stillframes/<filename>
https://files.explore.org/sn/<year>/<month>/<day>/<filename>.jpg

# Camera thumbnail variants
https://media.explore.org/stillframes/<name>__media_1920x1080.jpg
https://media.explore.org/stillframes/<name>__media_1280x720.jpg
https://media.explore.org/stillframes/<name>__media_853x480.jpg
https://media.explore.org/stillframes/<name>__media_498x280.jpg
```

---

## Python Client Usage

```python
from explore_org_client import ExploreOrgClient, fetch_all_camera_details, CAMERA_CATALOGUE

# Basic usage
client = ExploreOrgClient()

# === Listing cameras ===

# All 232 cameras (basic data from /initial)
all_cams = client.get_all_cameras()

# Only live cameras
live_cams = client.get_live_cameras()

# By category
bird_cams = client.get_cameras_by_channel("Birds")
bear_cams = client.get_cameras_by_channel("Bears")
africa_cams = client.get_cameras_by_channel("Africa")
ocean_cams = client.get_cameras_by_channel("Oceans")

# By cam-group (sub-category)
eagle_cams = client.get_cameras_by_cam_group("bald-eagles")
katmai_cams = client.get_cameras_by_cam_group("brown-bears")

# By location
iowa_cams = client.get_cameras_by_location("Iowa")
africa_cams = client.get_cameras_by_location("South Africa")

# By tag
cat_cams = client.get_cameras_by_tag("kitten")

# === Camera details ===

# Quick lookup (basic info from /initial)
cam = client.get_camera(199)
print(cam.title, cam.youtube_id, cam.is_live)
print(cam.youtube_watch_url)  # https://www.youtube.com/watch?v=IVmL3diwJuw

# Full details (makes one API call)
cam = client.get_camera_detail(199)
print(cam.description_text)
print(cam.latlong)
print(cam.partner_title)
print(cam.current_viewers)

# By slug
cam = client.get_camera_by_slug("decorah-eagles")

# === Snapshots ===

# Recent snapshots from all cameras
snaps = client.get_recent_snapshots(page=1, per_page=20)

# Snapshots for a specific camera
snaps = client.get_camera_snapshots(199, per_page=10)
for s in snaps:
    print(s.caption, s.full_url, s.created_at)

# === Search ===

results = client.search("katmai bears")
print(results["cameras"])   # list of matching cameras
print(results["blog_posts"])

# === Authentication ===

client.login("email@example.com", "password")
user = client.get_current_user()

# === Export ===

# Export to JSON (for pandas, etc.)
data = client.export_camera_list(include_offline=True)
import json
json.dump(data, open("cameras.json", "w"), indent=2)

# === Full detailed fetch (slow) ===
# Makes one API request per camera (~232 requests, ~60 seconds)
detailed_cams = fetch_all_camera_details(delay=0.1)

# === Offline catalogue ===
# Pre-fetched data embedded in the module - no API calls needed
from explore_org_client import CAMERA_CATALOGUE
for cam_id, info in CAMERA_CATALOGUE.items():
    if info["live"] and info["channel"] == "Africa":
        print(info["title"], info["youtube_id"])
        print(f"  Watch: https://www.youtube.com/watch?v={info['youtube_id']}")
```

### CLI Usage

```bash
# System summary
python3 explore_org_client.py summary

# List all live cameras
python3 explore_org_client.py live

# All cameras (live + offline)
python3 explore_org_client.py all

# List channels
python3 explore_org_client.py channels

# Cameras in a channel
python3 explore_org_client.py channel Bears
python3 explore_org_client.py channel Africa
python3 explore_org_client.py channel Birds
python3 explore_org_client.py channel Oceans

# Cameras in a cam-group
python3 explore_org_client.py group bald-eagles
python3 explore_org_client.py group brown-bears

# Camera details
python3 explore_org_client.py camera 199
python3 explore_org_client.py camera decorah-eagles

# Search
python3 explore_org_client.py search "katmai bears"
python3 explore_org_client.py search penguin

# Popular cameras by viewer count
python3 explore_org_client.py popular

# Recent snapshots for a camera
python3 explore_org_client.py snapshots 199 --n 5

# Export all cameras to JSON
python3 explore_org_client.py export -o cameras.json
python3 explore_org_client.py export --offline -o cameras_all.json
```

---

## Key Cameras

### Bears (Katmai - seasonal, live July-October)
| ID | Camera | YouTube ID | URL |
|----|--------|-----------|-----|
| 25 | Brooks Falls Brown Bears | `4qSRIIaOnLI` | https://explore.org/livecams/brown-bears/brown-bear-salmon-cam-brooks-falls |
| 229 | Brooks Falls Brown Bears Low | `53vUbxn5wl8` | https://explore.org/livecams/brown-bears/brooks-falls-brown-bears-low |
| 26 | Kat's River View | `0ikLzeuGeOA` | https://explore.org/livecams/brown-bears/brown-bear-salmon-cam-lower-river |
| 27 | The Riffles Bear Cam | `tp7PEBb2GCs` | https://explore.org/livecams/brown-bears/the-riffles-bear-cam |
| 50 | River Watch Bear Cam | `98SZ_UMAp_Q` | https://explore.org/livecams/brown-bears/river-watch-brown-bear-salmon-cams |
| 122 | Underwater Salmon Cam | `n712VZuZlrM` | https://explore.org/livecams/brown-bears/underwater-bear-cam-brown-bear-salmon-cams |

### Eagles
| ID | Camera | YouTube ID |
|----|--------|-----------|
| 199 | Decorah Eagles | `IVmL3diwJuw` |
| 108 | Decorah North Eagles | `GGIE1E-kaMQ` |
| 309 | Fraser Point Bald Eagle Nest 2 | `OY4V_AppZ6s` |
| 358 | Trempealeau Eagles | `8bMrSm0Ap20` |
| 134 | West End Bald Eagle Cam | `RmmAzrAkKqI` |
| 119 | Great Spirit Bluff Falcons | `w-Vjv7Cr9Ss` |

### African Wildlife
| ID | Camera | YouTube ID |
|----|--------|-----------|
| 284 | Tau Waterhole | `DsNtwGJXTTs` |
| 249 | Tembe Elephant Park | `VUJbDTIYlM4` |
| 248 | The Naledi Cat-EYE | `pZZst4BOpVI` |
| 250 | Olifants River | `_NXaovxB-Bk` |
| 276 | Nkorho Bush Lodge | `dIChLG4_WNs` |
| 247 | Rosie's Pan | `ItdXaWUVF48` |
| 364 | Boteti River Zebra Migration | `7hKbyXxWT2k` |
| 317 | Stony Point Penguin Colony | `ZRvngZiRx_g` |

### Underwater / Oceans
| ID | Camera | YouTube ID |
|----|--------|-----------|
| 2 | Tropical Fish - Coral Predators | `h0F818upkgI` |
| 3 | Blue Cavern Aquarium | `H59B9Uoewwg` |
| 8 | Tropical Reef Aquarium | `DHUnz4dyb54` |
| 7 | West Coast Sea Nettles - Jellyfish | `IYG9fnz40-E` |
| 59 | Shark Lagoon | `YT7lH6U68S4` |
| 96 | OrcaLab Main Cams | `hTOmWcmr2Tc` |
| 272 | Manatee Cam - Blue Spring (above) | `FbbHB9ka8Yg` |
| 273 | Manatee Cam - Blue Spring (underwater) | `h2GA3zrYeA0` |

---

## Notes

- **Seasonal cameras:** Many cameras (especially Katmai bears, panda cams) are only active during specific seasons. They remain on the site with YouTube IDs but streams show archived footage or a placeholder when inactive.
- **YouTube stream type:** Some cameras use YouTube live streams (24/7 continuous), others use YouTube premieres or on-demand videos. The `video_id` field works for both.
- **Viewer counts:** Real-time viewer counts (`current_viewers`) require calling `/get_livecam_info.json` individually for each camera; they are not included in the `/initial` bulk response.
- **Weather data:** Each camera with `weather_enabled: true` includes 10-day forecast data in the `/get_livecam_info.json` response.
- **Rate limiting:** The API appears to have no strict rate limiting during testing, but polite delays (0.1s per request) are recommended for bulk fetching.
- **Authentication:** A JWT token is required for write operations (favorites, comments, snapshots). The token is obtained via `POST /auth/login`.

---

## Files

- `explore_org_client.py` — Python API client with embedded camera catalogue
- `explore_org_README.md` — This documentation
