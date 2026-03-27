# Skiresort.info Webcam System — Reverse Engineering Report

## Overview

Skiresort.info is a TYPO3-based ski resort portal hosting 5,900+ webcams across 1,696+ ski resorts worldwide. This document describes all discovered API endpoints, data structures, and patterns derived from analysis of the live site.

**Site architecture:**
- Main portal: `https://www.skiresort.info` (TYPO3 CMS)
- Image/video CDN: `https://www.skiresort-service.com`
- Live streams: `https://webtv.feratel.com` (Feratel external provider)
- Thumbnails: `https://wtvthmb.feratel.com`

---

## Discovered Endpoints

### 1. Webcam Resort Listing — AJAX (JSON)

```
GET https://www.skiresort.info/weather/webcams/{geography}/ajaxlist.json
```

Optional query parameters:
- `tx_mgskiresort_pi1[resortlist][sword]` — Search query string
- `tx_mgskiresort_pi1[resortlist][Xsort]` — Sort order

**Headers required:**
```
Accept: application/json, text/javascript, */*; q=0.01
X-Requested-With: XMLHttpRequest
```

**Geography path values:**
- Omit for worldwide (`/weather/webcams/ajaxlist.json`)
- Country slugs: `austria`, `france`, `united-states`, `switzerland`, etc.
- Continent slugs: `europe`, `north-america`, `south-america`, `asia`, `australia-and-oceania`, `africa`
- Mountain range slugs: `alps`, `rocky-mountains`, `pyrenees`, etc.

**Response (JSON):**
```json
{
  "content": "<HTML string with resort cards>",
  "visible": ["570", "130", "138", ...],
  "pagebrowser_pageinfo_from": 1,
  "pagebrowser_pageinfo_to": 50
}
```

| Field | Type | Description |
|-------|------|-------------|
| `content` | string | HTML containing resort card divs |
| `visible` | array | All matching resort ID strings |
| `pagebrowser_pageinfo_from` | int | First item index on current page |
| `pagebrowser_pageinfo_to` | int | Last item index (equals `visible.length` on page 1) |

**Confirmed data points (Austria):** 291 total resorts
**Confirmed data points (worldwide):** 1,696 total resorts with webcams; 6,573 individual webcam feeds

---

### 2. Webcam Resort Listing — Paginated HTML

```
GET https://www.skiresort.info/weather/webcams/{geography}/page/{N}/
```

- 50 resorts per page
- Austria has 3+ pages (291 resorts)

---

### 3. Webcam Live Status

```
GET https://www.skiresort-service.com/typo3temp/_processed_/cams_archive/{folder}/{id}/status2.json
```

**Response (JSON):**
```json
{
  "status": {
    "live_available": true,
    "isOld": false,
    "last_thumbnail_success": 1774629093
  }
}
```

| Field | Type | Description |
|-------|------|-------------|
| `live_available` | bool | Whether live stream is currently active |
| `isOld` | bool | Whether the image is considered outdated |
| `last_thumbnail_success` | int | Unix timestamp of last successful image capture |

**Folder types:**
- `feratel_livestream` — Feratel live video streams
- `panomax_webcams` — Panomax 360° panoramic cameras
- `itwms_webcams_images` — ITWMS static webcam images
- `webcams` — Standard/direct webcam images
- `youtube_livestreams` — YouTube live stream embeds
- `roundshot_webcams` — Roundshot 360° panoramic cameras
- `webcamera_webcams` — Webcamera.pl feeds (Poland and Central Europe)

**Example:**
```
GET https://www.skiresort-service.com/typo3temp/_processed_/cams_archive/feratel_livestream/146/status2.json
→ {"status":{"live_available":true,"isOld":false,"last_thumbnail_success":1774629093}}
```

---

### 4. Webcam Archive

```
GET https://www.skiresort-service.com/typo3temp/_processed_/cams_archive/{folder}/{id}/archive2.json
```

Loaded by `webcamArchive.gz.js` on individual webcam detail pages.

**Response (JSON):**
```json
{
  "archive": {
    "2026": {
      "03": {
        "27": [
          {
            "resort_timestamp": 1774585889,
            "server_timestamp": 1774585889,
            "filename": "2026/03/27/05_31.jpg"
          },
          {
            "resort_timestamp": 1774591294,
            "server_timestamp": 1774591294,
            "filename": "2026/03/27/07_01.jpg"
          }
        ]
      }
    }
  },
  "status": {
    "live_available": true,
    "isOld": false,
    "last_thumbnail_success": 1774629093
  }
}
```

- Archives go back ~4-5 months
- Typically 9 images per day during ski season (every 90 min, daylight hours)
- Off-season: 1 image per day at midday

**Archive Image URL Pattern:**
```
# Full resolution
https://www.skiresort-service.com/typo3temp/_processed_/cams_archive/{folder}/{id}/{filename}
# e.g.: .../cams_archive/feratel_livestream/146/2026/03/27/11_31.jpg

# Thumbnail (smaller preview)
https://www.skiresort-service.com/typo3temp/_processed_/cams_archive/{folder}/{id}/{YYYY}/{MM}/{DD}/preview_{HH_MM}.jpg
# e.g.: .../cams_archive/feratel_livestream/146/2026/03/27/preview_11_31.jpg
```

Both full resolution and preview versions return HTTP 200.

**Example:**
```
GET https://www.skiresort-service.com/typo3temp/_processed_/cams_archive/feratel_livestream/146/archive2.json
→ {archive: {2026: {03: {27: [{filename: "2026/03/27/11_31.jpg", ...}, ...]}}}, status: {...}}
```

---

### 5. Webcam CDN Images (Current/Live Thumbnails)

Pattern derived from analyzing page HTML and verified by HTTP HEAD:

```
# Feratel live stream thumbnails
https://www.skiresort-service.com/typo3temp/_processed_/_cams_/livestream_37_{id}.jpg

# Panomax panoramic webcams
https://www.skiresort-service.com/typo3temp/_processed_/_cams_/panomax_reduced{id}.jpg

# Standard webcams
https://www.skiresort-service.com/typo3temp/_processed_/_cams_/webcam_{id}.jpg

# ITWMS webcams (hash-based, not predictable from ID alone)
https://www.skiresort-service.com/typo3temp/_processed_/_cams_/itwms_{md5hash}.jpg

# YouTube live stream thumbnails (video ID, not cam ID)
https://www.skiresort-service.com/typo3temp/_processed_/_cams_/youtube_{youtube_video_id}.jpg

# Roundshot 360° cameras
https://www.skiresort-service.com/typo3temp/_processed_/_cams_/roundshot_{id}.jpg

# Webcamera.pl feeds
https://www.skiresort-service.com/typo3temp/_processed_/_cams_/webcamera_{id}.jpg
```

Images are periodically refreshed. Add `?t={timestamp}` for cache-busting.

**Notes:**
- `itwms_webcams_images`: The hash in the filename is derived from the source camera URL (MD5). It is not predictable from the cam ID alone. Read from `data-src` attribute in page HTML.
- `youtube_livestreams`: The `data-id` attribute contains an internal sequential ID, but the image filename uses the actual YouTube video ID (11-character base64). Read from `data-src` attribute.

**OLD incorrect docs (superseded):**

---

### 6. Resort Webcam Page

```
GET https://www.skiresort.info/ski-resort/{resort-slug}/webcams/
```

Returns full HTML page with:
- All webcam `<div>` elements with `data-folder` and `data-id` attributes
- Webcam names, labels, and image URLs
- Resort timezone info
- Navigation links

**Webcam element attributes:**
```html
<div class="webcam-preview webcam-status"
     data-folder="feratel_livestream"
     data-id="146"
     data-resort-timezone='{"name":"Central European Standard Time","dstoffset":"0","rawoffset":"3600","timezoneid":"Europe/Vienna"}'
     id="wferatel146">
```

---

### 7. Individual Webcam Detail Page

```
GET https://www.skiresort.info/ski-resort/{resort-slug}/webcams/wcf{cam-id}/
```

Returns HTML page with hidden `<div>` elements containing full metadata:

```html
<div class="hidden" id="webcamId" data-value="146"></div>
<div class="hidden" id="webcamFolderName" data-value="feratel_livestream"></div>
<div class="hidden" id="webcamLiveURL" data-value="https://webtv.feratel.com/webtv/?design=v5&pg={GUID}&cam=5604"></div>
<div class="hidden" id="webcamLiveFullscreen" data-value="true"></div>
<div class="hidden" id="webcamRatio" data-value="0"></div>
<div class="hidden" id="webcamResortTimezone" data-value='{"name":"...","timezoneid":"Europe/Vienna"}'></div>
<div class="hidden" id="webcamArchiveDomain" data-value="https://www.skiresort-service.com"></div>
```

---

### 8. Feratel Live Stream (External Provider)

```
https://webtv.feratel.com/webtv/?design=v5&pg={PAGE_GUID}&cam={CAM_ID}
```

| Parameter | Description |
|-----------|-------------|
| `design` | Stream design version (`v5` observed) |
| `pg` | Feratel page GUID (UUID format, from webcam detail page) |
| `cam` | Feratel camera ID (integer) |

**Example:**
```
https://webtv.feratel.com/webtv/?design=v5&pg=20F52598-D6F3-448C-A38B-EC5071B837EA&cam=5604
```

---

### 9. Feratel Live Thumbnail

```
https://wtvthmb.feratel.com/thumbnails/{cam_id}.jpeg?t=38&dcsdesign=WTP_skiresort.de&design=v5
```

| Parameter | Description |
|-----------|-------------|
| `t` | Cache/version hint (observed as `38`) |
| `dcsdesign` | Design/partner identifier (`WTP_skiresort.de`) |
| `design` | Design version (`v5`) |

**Example:**
```
https://wtvthmb.feratel.com/thumbnails/5604.jpeg?t=38&dcsdesign=WTP_skiresort.de&design=v5
```

---

### 10. Snow Report Teaser (TYPO3 eID)

```
GET https://www.skiresort.info/index.php?eID=mg_skiresort_snowreportteaser&uid={resort_uid}&l=en&type={type}
```

| Parameter | Description |
|-----------|-------------|
| `eID` | TYPO3 extension ID: `mg_skiresort_snowreportteaser` |
| `uid` | Resort UID (integer, found in page HTML as `data-uid` attribute) |
| `l` | Language code (`en`, `de`, `fr`, etc.) |
| `type` | Report type (`snowreport`, `resortdata`) |

Returns HTML fragment with snow depth, lift status, and slope information.

---

### 11. Snow Reports Listing

```
GET https://www.skiresort.info/snow-reports/{country}/ajaxlist.json
GET https://www.skiresort.info/snow-reports/{country}/filter/open-ski-resorts/ajaxlist.json
GET https://www.skiresort.info/snow-reports/{country}/sorted/mountain-snow-depths/ajaxlist.json
GET https://www.skiresort.info/snow-reports/{country}/sorted/open-lifts/ajaxlist.json
GET https://www.skiresort.info/snow-reports/{country}/sorted/open-slopes/ajaxlist.json
GET https://www.skiresort.info/snow-reports/{country}/sorted/valley-snow-depths/ajaxlist.json
```

Returns the same JSON structure as the webcam listing (content, visible, pagebrowser info).

---

### 12. Other Discovered TYPO3 eID Endpoints

```
# Directions/routing
GET https://www.skiresort.info/index.php?eID=mg_skiresort_direction&action=getDirection&l=en

# Google Maps routing
GET https://www.skiresort.info/index.php?eID=mg_skiresort_gmaprouting&action=getWaypoints&...

# Filter/configurator (loads resort list with filters)
GET https://www.skiresort.info/index.php?eID=mg_skiresort_configurator&action=loadResortList&l=en

# Teaser tracking
GET https://www.skiresort.info/index.php?eID=mg_skiresort&action=teaserOut
```

---

## Data Structures

### Resort Object (from ajaxlist.json)

```python
{
    "name": "KitzSki – Kitzbühel/Kirchberg",
    "slug": "kitzski-kitzbuehel-kirchberg",
    "webcam_list_url": "https://www.skiresort.info/ski-resort/kitzski-kitzbuehel-kirchberg/webcams/",
    "webcam_count": 19,
    "location_breadcrumb": [
        {"slug": "europe", "name": "Europe"},
        {"slug": "austria", "name": "Austria"},
        {"slug": "tyrol", "name": "Tyrol"}
    ],
    "preview_images": [
        "https://www.skiresort-service.com/typo3temp/_processed_/_cams_/livestream_37_146.jpg"
    ],
    "webcam_previews": [
        {"folder": "feratel_livestream", "id": "146", "cdn_image_url": "..."}
    ]
}
```

### Webcam Object (from resort webcam page)

```python
{
    "folder": "feratel_livestream",
    "id": "146",
    "label": "Live stream",
    "name": "Hahnenkamm Berg (1,665 m) – Kitzbühel",
    "image_url": "https://www.skiresort-service.com/typo3temp/_processed_/_cams_/livestream_37_146.jpg",
    "image_url_mobile": "https://www.skiresort-service.com/typo3temp/_processed_/_cams_/livestream_37_146.jpg",
    "alt_text": "Hahnenkamm Berg (1,665 m) – Kitzbühel",
    "detail_url": "https://www.skiresort.info/ski-resort/kitzski-kitzbuehel-kirchberg/webcams/wcf146/",
    "element_id": "wferatel146",
    "cdn_image_url": "https://www.skiresort-service.com/typo3temp/_processed_/_cams_/livestream_37_146.jpg",
    "status_url": "https://www.skiresort-service.com/typo3temp/_processed_/cams_archive/feratel_livestream/146/status2.json",
    "timezone": {
        "name": "Central European Standard Time",
        "dstoffset": "0",
        "rawoffset": "3600",
        "timezoneid": "Europe/Vienna"
    },
    "is_live_stream": true,
    "is_360": false
}
```

### Webcam Detail Object (from wcf detail page)

```python
{
    "webcam_id": "146",
    "folder": "feratel_livestream",
    "title": "Live stream Hahnenkamm Berg – Kitzbühel",
    "archive_domain": "https://www.skiresort-service.com",
    "live_stream_url": "https://webtv.feratel.com/webtv/?design=v5&pg=20F52598-D6F3-448C-A38B-EC5071B837EA&cam=5604",
    "is_live": true,
    "live_fullscreen": true,
    "aspect_ratio": "0",
    "feratel_cam_id": "5604",
    "feratel_page_guid": "20F52598-D6F3-448C-A38B-EC5071B837EA",
    "feratel_thumbnail_url": "https://wtvthmb.feratel.com/thumbnails/5604.jpeg?t=38&dcsdesign=WTP_skiresort.de&design=v5",
    "cdn_image_url": "https://www.skiresort-service.com/typo3temp/_processed_/_cams_/livestream_37_146.jpg",
    "status_url": "https://www.skiresort-service.com/typo3temp/_processed_/cams_archive/feratel_livestream/146/status2.json",
    "timezone": {
        "name": "Central European Standard Time",
        "dstoffset": "0",
        "rawoffset": "3600",
        "timezoneid": "Europe/Vienna"
    },
    "resort_slug": "kitzski-kitzbuehel-kirchberg"
}
```

### Webcam Status Object

```python
{
    "live_available": true,
    "isOld": false,
    "last_thumbnail_success": 1774629093,
    "folder": "feratel_livestream",
    "cam_id": "146",
    "status_url": "https://www.skiresort-service.com/typo3temp/_processed_/cams_archive/feratel_livestream/146/status2.json",
    "image_url": "https://www.skiresort-service.com/typo3temp/_processed_/_cams_/livestream_37_146.jpg"
}
```

---

## Webcam URL Patterns Summary

### Current Live Images (CDN)

All images served from `https://www.skiresort-service.com/typo3temp/_processed_/_cams_/`

| Folder Type | Image Filename Pattern | Notes |
|-------------|------------------------|-------|
| `feratel_livestream` | `livestream_37_{id}.jpg` | Most common in Alps |
| `panomax_webcams` | `panomax_reduced{id}.jpg` | 360° panoramas |
| `webcams` | `webcam_{id}.jpg` | Standard webcams |
| `itwms_webcams_images` | `itwms_{md5hash}.jpg` | Hash not predictable from ID |
| `youtube_livestreams` | `youtube_{video_id}.jpg` | YouTube video ID, not cam ID |
| `roundshot_webcams` | `roundshot_{id}.jpg` | 360° roundshot panoramas |
| `webcamera_webcams` | `webcamera_{id}.jpg` | Webcamera.pl (Poland etc.) |

### Archive Images

Base: `https://www.skiresort-service.com/typo3temp/_processed_/cams_archive/`

| Resource | URL Pattern |
|----------|-------------|
| Archive index | `{base}/{folder}/{id}/archive2.json` |
| Live status | `{base}/{folder}/{id}/status2.json` |
| Full archive image | `{base}/{folder}/{id}/{YYYY}/{MM}/{DD}/{HH_MM}.jpg` |
| Archive thumbnail | `{base}/{folder}/{id}/{YYYY}/{MM}/{DD}/preview_{HH_MM}.jpg` |

---

## Webcam Listing URL Patterns

| Geography | URL |
|-----------|-----|
| Worldwide | `/weather/webcams/ajaxlist.json` |
| Country | `/weather/webcams/austria/ajaxlist.json` |
| Continent | `/weather/webcams/europe/ajaxlist.json` |
| Mountain range | `/weather/webcams/alps/ajaxlist.json` |
| Paginated | `/weather/webcams/austria/page/2/` |
| Search | `/weather/webcams/ajaxlist.json?tx_mgskiresort_pi1[resortlist][sword]=kitzbuhel` |

---

## Region Taxonomy

### Continents
- `europe`, `north-america`, `south-america`, `asia`, `australia-and-oceania`, `africa`

### Countries (selected)
- `austria`, `france`, `switzerland`, `italy`, `germany`, `norway`, `sweden`, `finland`
- `united-states`, `canada`, `chile`, `argentina`
- `japan`, `china`, `south-korea`
- `new-zealand`, `australia`
- Full list in client: `COUNTRIES` constant

### Mountain Ranges
- `alps`, `rocky-mountains`, `pyrenees`, `andes`, `himalayas`, `caucasus-mountains`
- `scandinavian-mountains`, `japanese-alps`, `carpathian-mountains-karpaty`
- Full list in client: `MOUNTAIN_RANGES` constant

---

## Installation

```bash
pip install requests beautifulsoup4
```

Minimum: Python 3.7+, `requests` only required (falls back to urllib).

---

## Quick Start

```python
from skiresort_webcams_client import SkiresortWebcamClient

client = SkiresortWebcamClient(rate_limit_delay=1.0)

# --- List resorts ---

# All worldwide resorts with webcams (1696+)
result = client.list_resorts_with_webcams()
print(f"Total resorts: {result['total_visible']}")

# By country (e.g., Austria: 291 resorts)
result = client.list_resorts_by_country("austria")
for resort in result["resorts"]:
    print(resort["name"], resort.get("webcam_count"))

# Paginate through all resorts in a country
for resort in client.iterate_all_resorts("france"):
    print(resort["name"])

# --- Search ---
results = client.search_resorts("innsbruck")
for r in results:
    print(r["name"], r["webcam_list_url"])

# --- Resort webcams ---
resort_data = client.get_resort_webcams("kitzski-kitzbuehel-kirchberg")
print(f"Resort: {resort_data['resort_name']}")
print(f"Total webcams: {len(resort_data['webcams'])}")
for cam in resort_data["webcams"]:
    print(f"  [{cam['label']}] {cam['name']}")
    print(f"  Image: {cam['image_url']}")
    print(f"  Status: {cam['status_url']}")

# --- Webcam detail ---
detail = client.get_webcam_detail("kitzski-kitzbuehel-kirchberg", "146")
print(f"Live stream: {detail.get('live_stream_url')}")
print(f"Feratel cam: {detail.get('feratel_cam_id')}")
print(f"Thumbnail: {detail.get('feratel_thumbnail_url')}")

# --- Live status ---
status = client.get_webcam_status("feratel_livestream", "146")
print(f"Live: {status['live_available']}, Is old: {status['isOld']}")

# --- Direct URL building (no HTTP required) ---
print(SkiresortWebcamClient.build_cdn_image_url("feratel_livestream", "146"))
print(SkiresortWebcamClient.build_status_url("panomax_webcams", "659"))
print(SkiresortWebcamClient.build_feratel_stream_url("5604", "20F52598-D6F3-448C-A38B-EC5071B837EA"))

# --- Webcam archive ---

# Fetch full archive index (dates + filenames, going back ~4 months)
archive = client.get_webcam_archive("feratel_livestream", "146")
for year, months in archive["archive"].items():
    for month, days in months.items():
        for day, entries in days.items():
            for e in entries:
                print(e["filename"])  # e.g. "2026/03/27/11_31.jpg"

# Get URL for a specific archived image
img_url = client.get_archive_image_url("feratel_livestream", "146", "2026/03/27/11_31.jpg")
thumb_url = client.get_archive_image_url("feratel_livestream", "146", "2026/03/27/11_31.jpg", thumbnail=True)

# Get the most recent archived image URL
latest = client.get_latest_archive_image_url("feratel_livestream", "146")

# Iterate archive images for a specific day
for img in client.iter_archive_images("feratel_livestream", "146", year=2026, month=3, day=27):
    print(img["filename"], img["image_url"])

# --- YouTube webcams (North America) ---
big_sky = client.get_resort_webcams("big-sky-resort")
for cam in big_sky["webcams"]:
    if cam["folder"] == "youtube_livestreams":
        yt_id = SkiresortWebcamClient.extract_youtube_id(cam["folder"], cam.get("image_url", ""))
        print(f"YouTube stream: https://www.youtube.com/watch?v={yt_id}")
```

---

## Pagination Details

The main listing pages use 50 resorts per page. The `ajaxlist.json` endpoint returns all visible resort IDs in the `visible` array regardless of page, but the HTML `content` field is paginated.

To get a specific page via the JSON endpoint, request the paginated HTML URL with `ajaxlist.json`:

```
/weather/webcams/austria/page/2/ajaxlist.json  → but returns same data as page 1
```

The correct way to paginate is to use the HTML pages:
```
/weather/webcams/austria/           → page 1
/weather/webcams/austria/page/2/    → page 2
/weather/webcams/austria/page/3/    → page 3
```

And use `ajaxlist.json` on each of those URLs to get JSON.

---

## Rate Limiting

The site does not appear to enforce aggressive rate limiting, but the following headers should be used to avoid blocks:

```python
DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 ...",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}
```

Recommended: 1-2 seconds between requests.

---

## Live Webcam Providers

The site aggregates webcams from multiple providers. The `data-folder` attribute identifies the provider:

| Folder | Provider | Stream Type | Image Prefix |
|--------|----------|-------------|--------------|
| `feratel_livestream` | Feratel (Austria/Germany) | Live MJPEG / HLS via iframe | `livestream_37_{id}` |
| `panomax_webcams` | Panomax (panoramic cams) | Static + 360° interactive | `panomax_reduced{id}` |
| `itwms_webcams_images` | ITWMS | Refreshing JPEG | `itwms_{md5hash}` |
| `webcams` | Various direct feeds | Refreshing JPEG | `webcam_{id}` |
| `youtube_livestreams` | YouTube (embedded) | HLS live stream | `youtube_{video_id}` |
| `roundshot_webcams` | Roundshot | 360° panorama | `roundshot_{id}` |
| `webcamera_webcams` | Webcamera.pl | Refreshing JPEG | `webcamera_{id}` |

### Feratel Integration

Feratel webcams embed a player via:
```
https://webtv.feratel.com/webtv/?design=v5&pg={PAGE_GUID}&cam={CAM_ID}
```

The `PAGE_GUID` is unique to each webcam's configured page on the Feratel platform and can only be found by fetching the individual webcam detail page (`/webcams/wcf{id}/`).

---

## Notes on `itwms_webcams_images` URLs

The ITWMS webcam images use an MD5 hash in the filename:
```
https://www.skiresort-service.com/typo3temp/_processed_/_cams_/itwms_{md5hash}.jpg
```

The hash is derived from the source URL of the camera feed, so it cannot be predicted without knowing the original source URL. These images are found directly on the resort webcam page via `data-src` attributes.

---

## JavaScript Architecture Notes

The site loads two relevant JS bundles:
- `jsFooterV3.gz.js` — Main site JS (status2.json loading, webcam status via IntersectionObserver)
- `webcamArchive.gz.js` — Archive viewer JS (loaded only on individual webcam detail pages)

The `webcamArchive.gz.js` bundle (77KB) reveals:
- The archive endpoint is `archive2.json` (not `archive.json` — that returns 404)
- Preview/thumbnail images use `preview_` prefix before the time component
- The JavaScript variable `a` is set to `{archive_domain}/typo3temp/_processed_/cams_archive/`
- Full archive image URL: `${a}${webcamFolderName}/${webcamId}/${filename}`
- Thumbnail URL: `${a}${webcamFolderName}/${webcamId}/${date}/preview_${time}`

The JavaScript bundle (`jsFooterV3.gz.js`) reveals:

1. **ajaxURL**: `"index.php?type=997"` — used for teaser/teaserOut tracking
2. **Filter form**: `tx_mgskiresort_pi1[resortlist][sword]` — search query
3. **Sort param**: `tx_mgskiresort_pi1[resortlist][Xsort]`
4. **Pagination**: Standard TYPO3 pagebrowser (forward/back links in HTML)
5. **Webcam status**: Loaded lazily via IntersectionObserver
6. **Cache**: `webcamDataCache` Map to avoid duplicate fetches
7. **Dispatch**: `document.dispatchEvent(new Event("loadWebcamStatus"))` triggers status loading

---

## Verified Working Examples (March 2026)

```bash
# Webcam status
curl "https://www.skiresort-service.com/typo3temp/_processed_/cams_archive/feratel_livestream/146/status2.json"
# → {"status":{"live_available":true,"isOld":false,"last_thumbnail_success":1774629093}}

# Webcam status for standard webcam
curl "https://www.skiresort-service.com/typo3temp/_processed_/cams_archive/webcams/30575/status2.json"
# → {"status":{"live_available":true,"isOld":false,"last_thumbnail_success":1774627598}}

# YouTube livestream status
curl "https://www.skiresort-service.com/typo3temp/_processed_/cams_archive/youtube_livestreams/1036/status2.json"
# → {"status":{"live_available":true,"isOld":false,"last_thumbnail_success":1774627895}}

# Archive index for a webcam (returns 4+ months of history)
curl "https://www.skiresort-service.com/typo3temp/_processed_/cams_archive/feratel_livestream/146/archive2.json"
# → {"archive":{"2025":{"12":{"01":[{"filename":"2025/12/01/11_41.jpg",...}],...}}},"status":{...}}

# Archive image (full resolution)
curl -I "https://www.skiresort-service.com/typo3temp/_processed_/cams_archive/feratel_livestream/146/2026/03/27/11_31.jpg"
# → HTTP/2 200

# Archive image (thumbnail)
curl -I "https://www.skiresort-service.com/typo3temp/_processed_/cams_archive/webcams/30575/2025/10/28/preview_11_33.jpg"
# → HTTP/2 200

# Current live image - feratel
curl -I "https://www.skiresort-service.com/typo3temp/_processed_/_cams_/livestream_37_146.jpg"
# → HTTP/2 200

# Current live image - panomax (note: panomax_reduced, NOT livestream_37)
curl -I "https://www.skiresort-service.com/typo3temp/_processed_/_cams_/panomax_reduced4052641.jpg"
# → HTTP/2 200

# Current live image - YouTube thumbnail
curl -I "https://www.skiresort-service.com/typo3temp/_processed_/_cams_/youtube_dMr-Jt_K3Cc.jpg"
# → HTTP/2 200

# Austria resort list (JSON)
curl -H "X-Requested-With: XMLHttpRequest" \
     "https://www.skiresort.info/weather/webcams/austria/ajaxlist.json"
# → {"content":"<html>...","visible":["570","130",...291 IDs...],"pagebrowser_pageinfo_from":1,"pagebrowser_pageinfo_to":291}

# Worldwide resort list
curl -H "X-Requested-With: XMLHttpRequest" \
     "https://www.skiresort.info/weather/webcams/ajaxlist.json"
# → 1696 visible resort IDs
```

---

## File Structure

```
skiresort_webcams_client.py    Main Python client
skiresort_webcams_README.md    This documentation
```
