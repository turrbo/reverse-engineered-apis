# USGS Volcano Webcams & Monitoring API Client

Reverse-engineered Python client for all publicly accessible USGS volcano webcam and monitoring data systems. No API key, login, or browser required.

---

## API Systems Discovered

### System 1 — VHP VSC APIs
**Base:** `https://volcanoes.usgs.gov/vsc/api/`

Five sub-APIs documented at `https://volcanoes.usgs.gov/vsc/api/`:

| Sub-API | Base URL | Purpose |
|---------|----------|---------|
| Volcano API | `/vsc/api/volcanoApi/` | US/worldwide volcano metadata, status, GeoJSON |
| Observatory API | `/vsc/api/observatoryApi/` | Observatory info and geographic boundaries |
| HANS API (legacy) | `/vsc/api/hansApi/` | Hazard notices, VONAs |
| HVO Webcams API | `/vsc/api/hvoWebcamsApi/` | Hawaii camera metadata (currently returns empty) |
| Volcano Message API | `/vsc/api/volcanoMessageApi/` | Short eruption snippets (Kilauea only) |

> Note: "These resources are freely available but are designed to support USGS applications. No guarantee of continuing support should be assumed." — contact mjrandall@usgs.gov

---

### System 2 — HANS Public API
**Base:** `https://volcanoes.usgs.gov/hans-public/api/`

A cleaner, newer facade documented at `https://volcanoes.usgs.gov/hans-public/api/`:

| Sub-API | Base URL | Purpose |
|---------|----------|---------|
| Volcano API | `/hans-public/api/volcano/` | Elevated, monitored volcanoes; CAP data |
| Notice API | `/hans-public/api/notice/` | Retrieve, search, filter notices |
| Map API | `/hans-public/api/map/` | XML status for mapping |
| Search API | `/hans-public/api/search/` | Full-text search over historical notices |

---

### System 3 — HVO Legacy Webcam System
**Base:** `https://volcanoes.usgs.gov/cams/`

Every camera has a single current JPEG updated every 1–10 minutes:
```
https://volcanoes.usgs.gov/cams/{CAMID}/images/M.jpg
```
A sidecar JavaScript file carries the last-updated timestamp:
```
https://volcanoes.usgs.gov/cams/{CAMID}/images/js.js
```
Content: `var datetime = "2026-03-27 06:20:08 (HST)"; var frames = new Array("M");`

Viewer page: `https://volcanoes.usgs.gov/cams/panorama.php?cam={CAMID}`

---

### System 4 — AVO Ashcam REST API
**Base:** `https://avo.alaska.edu/ashcam-api/`
**Documentation:** `https://avo.alaska.edu/ashcam-api/`

386 cameras with a complete image archive back to ~2020.

**Sub-APIs:**
```
GET {base}/webcamApi/webcams                      — all cameras
GET {base}/webcamApi/webcam/{CODE}                — single camera
GET {base}/webcamApi/geojson?lat1=&lat2=&long1=&long2=  — GeoJSON bounding box
GET {base}/webcamApi/volcanoWebcams?volcano={CD}  — cameras for a volcano
GET {base}/webcamApi/archivedWebcams              — cameras with archives
GET {base}/webcamApi/archive/webcam/{CODE}        — archive metadata

GET {base}/imageApi/webcam/{CODE}/{DAYS}/{ORDER}/{LIMIT}       — last N days
GET {base}/imageApi/webcam/{CODE}/{START_TS}/{END_TS}/{ORDER}/{LIMIT}  — time range
GET {base}/imageApi/webcam?webcamCode=&startTimestamp=&endTimestamp=&order=&limit=
GET {base}/imageApi/webcam/{CODE}                              — all images
GET {base}/imageApi/recent/{LIMIT}                             — latest N images
GET {base}/imageApi/interesting/{DAYS}                         — volcanic activity images
GET {base}/imageApi/uninteresting/{DAYS}                       — quiet images
GET {base}/imageApi/archive/webcam?webcamCode=&startTimestamp=&endTimestamp=&order=&limit=
```

---

### System 5 — VolcView API (CVO/YVO mirror)
**Base:** `https://volcview.wr.usgs.gov/ashcam-api/`

Mirrors the AVO Ashcam API structure. Used by CVO and YVO cameras. Identical endpoints; fewer historical images than the primary AVO host.

---

## Observatories and Camera Counts

| Observatory | Abbr | Volcanoes | Cameras | System |
|-------------|------|-----------|---------|--------|
| Hawaii Volcano Observatory | HVO | Kilauea, Mauna Loa | 31 | Legacy `/cams/` |
| Alaska Volcano Observatory | AVO | 20+ Alaska volcanoes | 386 | Ashcam REST |
| Cascades Volcano Observatory | CVO | St. Helens, Rainier, Baker, Adams, Hood, Glacier Peak, Three Sisters, Crater Lake, Shasta | ~30 | VolcView REST |
| Yellowstone Volcano Observatory | YVO | Yellowstone | 3 | VolcView REST |
| California Volcano Observatory | CalVO | Shasta (shared w/ CVO) | ~1 | VolcView REST |

---

## Image URL Patterns

### HVO
```
https://volcanoes.usgs.gov/cams/{CAMID}/images/M.jpg
```
Only one size served. No thumbnail variants.

### AVO (current)
```
https://avo.alaska.edu/ashcam-api/images/{CAMCODE}/current.jpg
https://avo.alaska.edu/ashcam-api/images/{CAMCODE}/current-medium.jpg
https://avo.alaska.edu/ashcam-api/images/{CAMCODE}/current-thumb.jpg
```

### AVO (archive)
```
https://avo.alaska.edu/ashcam-api/images/{CAMCODE}/{YYYY}/{DOY}/{CAMCODE}-{YYYYMMDD}T{HHMMSS}Z.jpg
```
- `DOY` = numeric day-of-year with no leading zeros (e.g. `85` for March 27)
- Timestamp is UTC, `Z` suffix
- Example: `images/augustine/2026/85/augustine-20260327T172000Z.jpg`

### AVO (clear/reference image)
```
https://avo.alaska.edu/ashcam-api/images/clear/{CAMCODE}/{CAMCODE}-{YYYYMMDD}T{HHMMSS}Z.jpg
```
"Clear" images are the best daytime images manually selected by USGS staff.

### VolcView (CVO/YVO)
```
https://volcview.wr.usgs.gov/ashcam-api/images/webcams/{CAMCODE}/current.jpg
```
Note: VolcView uses `/images/webcams/{CAMCODE}/` while AVO uses `/images/{CAMCODE}/`.

### VHP station monitoring plots
```
https://volcanoes.usgs.gov/vsc/captures/{volcano_name}/{STATION}-{PERIOD}.png
```
Example: `https://volcanoes.usgs.gov/vsc/captures/kilauea/AHUD-24h.png`

---

## Volcano Status / Alert Levels

Fetch current status via:
```python
GET https://volcanoes.usgs.gov/vsc/api/volcanoApi/vhpstatus/{vnum_or_volcanoCd}
GET https://volcanoes.usgs.gov/vsc/api/volcanoApi/vhpstatus  # all volcanoes
GET https://volcanoes.usgs.gov/vsc/api/volcanoApi/geojson
GET https://volcanoes.usgs.gov/hans-public/api/volcano/getElevatedVolcanoes
```

Alert level scale:
| Alert Level | Color Code | Meaning |
|-------------|-----------|---------|
| NORMAL | GREEN | Background activity |
| ADVISORY | YELLOW | Elevated unrest above background levels |
| WATCH | ORANGE | Eruption with minimal hazard beyond the immediate vicinity, OR eruption with significant hazard |
| WARNING | RED | Eruption is imminent with significant hazard to life and property |
| UNASSIGNED | UNASSIGNED | Not currently monitored or not yet assessed |

---

## Complete Endpoint Reference

### VHP Volcano API (`/vsc/api/volcanoApi/`)

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/volcanoesUS` | All US volcanoes |
| GET | `/volcanoesGVP` | Worldwide volcanoes (~1470, Smithsonian GVP) |
| GET | `/vhpstatus` | Status for all US volcanoes |
| GET | `/vhpstatus?obs={obs}` | Status filtered by observatory |
| GET | `/vhpstatus/{id}` | Status for one volcano (vnum or volcanoCd) |
| GET | `/geojson` | All US volcanoes as GeoJSON FeatureCollection |
| GET | `/geojson?lat1=&lat2=&long1=&long2=` | Bounding-box GeoJSON |
| GET | `/elevated` | Volcanoes with elevated activity |
| GET | `/elevated?obs={obs}` | Elevated filtered by observatory |
| GET | `/volcano?vnum={v}` | Single volcano metadata by vnum |
| GET | `/volcano?volcanoCd={cd}` | Single volcano by USGS code |
| GET | `/volcanoStationPlots/{vnum}` | Monitoring station plots (seismo, GPS, tilt) |

### VHP Observatory API (`/vsc/api/observatoryApi/`)

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/observatories` | All observatories with boundary polygons |
| GET | `/observatory/{OBS}` | Single observatory (AVO|CalVO|CVO|HVO|NMI|YVO) |

### VHP HANS API — legacy (`/vsc/api/hansApi/`)

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/notice/{notice_id}` | Single notice by identifier |
| GET | `/noticeSection/{section_id}` | Single-volcano notice section |
| GET | `/vonas` | All VONAs, newest first |
| GET | `/vonas?obs={obs}` | VONAs filtered by observatory |
| GET | `/vonas/{DAYS}` | VONAs from last N days |
| GET | `/newest` | Newest notice from each observatory |
| GET | `/volcNewest/{vnum}` | Newest notice for a specific volcano |

### HANS Public API — volcano (`/hans-public/api/volcano/`)

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/getUSVolcanoes` | All US volcanoes |
| GET | `/getVolcano/{id}` | Single volcano by vnum or volcanoCd |
| GET | `/getElevatedVolcanoes` | Currently elevated volcanoes |
| GET | `/getMonitoredVolcanoes` | Actively monitored volcanoes |
| GET | `/getCapElevated` | CAP (Common Alerting Protocol) for highly elevated |
| GET | `/newestForVolcano/{id}` | Notice sections for newest notice for a volcano |

### HANS Public API — notice (`/hans-public/api/notice/`)

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/getNotice/{notice_id}` | HTML for a notice |
| GET | `/getNoticeFormatted/{notice_id}/{fmt}` | Notice in json\|html\|text\|sms |
| GET | `/getNoticeParts/{notice_id}` | JSON sections of a notice |
| GET | `/getRecentNotices` | All notices from last ~month |
| GET | `/getNewestOrRecent` | Newest per observatory or recent |
| GET | `/getNoticesLastDayHTML` | Last 24 hours HTML |
| GET | `/recent/{OBS}/{DAYS}` | Notices by observatory (1–7 days) |
| GET | `/getVona/{notice_id}` | VONA HTML |
| GET | `/getVonasWithinLastYear` | VONAs from last year |
| GET | `/getDailySummaryData` | Daily summary JSON |

### HANS Public API — search (`/hans-public/api/search/`)

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/getHansNoticeTypes` | All notice type codes |
| GET | `/getAllVolcanoesWithNotice` | Volcanoes with any notice |
| POST | `/search` | Full-text search with JSON body |
| POST | `/preflight` | Count results before search |

Search body fields: `obsAbbr`, `noticeTypeCd`, `volcCd`, `startUnixtime`, `endUnixtime`, `searchText`, `pageIndex`

Notice type codes: `WU` (Weekly Update), `DU` (Daily Update), `IS` (Information Statement), `VAN` (Volcanic Activity Notice), `VONA` (Aviation Notice)

### AVO Ashcam API — image (`/imageApi/`)

`ORDER` = `newestFirst` | `oldestFirst`
`LIMIT` = 0 returns all results within range

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/recent/{LIMIT}` | Latest N images across all cameras |
| GET | `/webcam/{CODE}/{DAYS}/{ORDER}/{LIMIT}` | Last N days |
| GET | `/webcam/{CODE}/{START_TS}/{END_TS}/{ORDER}/{LIMIT}` | Time range |
| GET | `/webcam?webcamCode=&startTimestamp=&endTimestamp=&order=&limit=` | Query-param time range |
| GET | `/webcam/{CODE}` | All images for a camera |
| GET | `/interesting` | All images with volcanic activity |
| GET | `/interesting/{DAYS}` | Volcanic activity images, last N days |
| GET | `/uninteresting/{DAYS}` | No-activity images, last N days (max 5000) |
| GET | `/archive/webcam?webcamCode=&startTimestamp=&endTimestamp=&order=&limit=` | Archive query |

`interestingCode` values: `N` = no activity, `V` = volcanic activity detected, `U` = unknown/uncoded

### Volcano Message API (`/vsc/api/volcanoMessageApi/`)

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/volcanoNewest/{vnum}` | Most recent message |
| GET | `/volcanoRecent/{vnum}` | Recent messages |
| GET | `/volcanoRecent/{vnum}?limit={n}` | Last N messages |
| GET | `/volcanoRecent/{vnum}?daysBack={n}` | Messages from last N days |

Currently only vnum `332010` (Kilauea) has messages.

---

## Example JSON Responses

### VHP status record
```json
{
  "vName": "Kilauea",
  "lat": 19.421,
  "long": -155.287,
  "vnum": "332010",
  "volcanoCd": "hi3",
  "vUrl": "https://www.usgs.gov/volcanoes/kilauea",
  "vImage": "https://volcanoes.usgs.gov/vsc/images/kilauea/kilauea.jpg",
  "obs": "hvo",
  "region": "Hawaii",
  "noticeId": "DOI-USGS-HVO-2026-03-26T18:04:33+00:00",
  "noticeSynopsis": "HVO Kilauea ORANGE/WATCH - The Halema'uma'u eruption is paused.",
  "alertLevel": "WATCH",
  "colorCode": "ORANGE",
  "statusIconUrl": "https://volcanoes.usgs.gov/images/icons/map/orange_watch.png",
  "alertDate": "2026-03-26 19:14:39",
  "noticeUrl": "https://volcanoes.usgs.gov/hans2/view/notice/DOI-USGS-HVO-2026-03-26T18:04:33+00:00",
  "noticeSectionData": "https://volcanoes.usgs.gov/vsc/api/hansApi/noticeSection/...",
  "nvewsThreat": "Very High Threat"
}
```

### AVO webcam record
```json
{
  "webcamCode": "augustine",
  "webcamName": "Augustine [Homer, 709 ft]",
  "latitude": 59.363,
  "longitude": -153.435,
  "elevationM": 216.0,
  "bearingDeg": 230,
  "vnum": "313010",
  "vName": "Augustine",
  "hasImages": "Y",
  "imageTotal": 111248,
  "firstImageDate": "Thu, 12 Aug 2021 11:14:00 +0000",
  "firstImageTimestamp": 1628766840,
  "lastImageDate": "Fri, 27 Mar 2026 17:20:00 +0000",
  "lastImageTimestamp": 1774632000,
  "currentImageUrl": "https://avo.alaska.edu/ashcam-api/images/augustine/current.jpg",
  "currentMediumImageUrl": "https://avo.alaska.edu/ashcam-api/images/augustine/current-medium.jpg",
  "currentThumbImageUrl": "https://avo.alaska.edu/ashcam-api/images/augustine/current-thumb.jpg",
  "clearImageUrl": "https://avo.alaska.edu/ashcam-api/images/clear/augustine/augustine-20251216T210000Z.jpg",
  "newestImage": {
    "imageId": 31353140,
    "imageTimestamp": 1774632000,
    "imageDate": "Fri, 27 Mar 2026 17:20:00 +0000",
    "isNighttimeInd": "N",
    "imageUrl": "https://avo.alaska.edu/ashcam-api/images/augustine/2026/85/augustine-20260327T172000Z.jpg",
    "interestingCode": "U"
  },
  "suninfo": {
    "civil_twilight_sunrise": "Fri, 27 Mar 2026 16:52:15 +0000",
    "civil_twilight_sunset": "Sat, 28 Mar 2026 06:20:47 +0000"
  },
  "organization": "USGS",
  "isPublic": "Y",
  "hasArchiveImages": "N",
  "volcanoes": ["ak8"],
  "lists": []
}
```

### AVO image record
```json
{
  "imageId": 31352779,
  "md5": "78a2dcff3c5f95efda1db8bc3f5970db",
  "webcamCode": "okif",
  "newestForWebcam": "Y",
  "imageTimestamp": 1774630860,
  "imageDate": "Fri, 27 Mar 2026 17:01:00 +0000",
  "isNighttimeInd": "N",
  "interestingCode": "U",
  "imageUrl": "https://avo.alaska.edu/ashcam-api/images/okif/2026/85/okif-20260327T170100Z.jpg",
  "suninfo": {
    "civil_twilight_sunrise": "Fri, 27 Mar 2026 16:20:26 +0000",
    "civil_twilight_sunset": "Sat, 28 Mar 2026 06:13:17 +0000"
  }
}
```

### HANS Public API elevated volcano record
```json
{
  "obs_fullname": "Alaska Volcano Observatory",
  "obs_abbr": "avo",
  "volcano_name": "Great Sitkin",
  "vnum": "311120",
  "notice_type_cd": "DU",
  "notice_identifier": "DOI-USGS-AVO-2026-03-26T19:23:42+00:00",
  "sent_utc": "2026-03-26 19:26:28",
  "sent_unixtime": 1774553188,
  "color_code": "ORANGE",
  "alert_level": "WATCH",
  "notice_url": "https://volcanoes.usgs.gov/hans-public/notice/DOI-USGS-AVO-2026-03-26T19:23:42+00:00",
  "notice_data": "https://volcanoes.usgs.gov/hans-public/api/notice/getNotice/DOI-USGS-AVO-2026-03-26T19:23:42+00:00"
}
```

---

## HVO Camera IDs

| Cam ID | Volcano | Region | Thermal |
|--------|---------|--------|---------|
| B1cam | Kilauea | Summit | No |
| B2cam | Kilauea | Summit | No |
| F1cam | Kilauea | Summit | **Yes** |
| K2cam | Kilauea | Summit | No |
| KPcam | Kilauea | Summit | No |
| KWcam | Kilauea | Summit | No |
| S2cam | Kilauea | Summit | No |
| V1cam | Kilauea | Summit | No |
| V2cam | Kilauea | Summit | No |
| V3cam | Kilauea | Summit | No |
| HPcam | Kilauea | East Rift Zone | No |
| KOcam | Kilauea | East Rift Zone | No |
| MUcam | Kilauea | East Rift Zone | No |
| PEcam | Kilauea | East Rift Zone | No |
| PWcam | Kilauea | East Rift Zone | No |
| R3cam | Kilauea | East Rift Zone | No |
| PGcam | Kilauea | Lower East Rift Zone | No |
| MITDcam | Kilauea | Southwest Rift Zone | No |
| S1cam | Kilauea | Southwest Rift Zone | No |
| MOcam | Mauna Loa | South Caldera | No |
| SPcam | Mauna Loa | South Caldera | No |
| MSTcam | Mauna Loa | South Caldera | **Yes** |
| HLcam | Mauna Loa | Summit | No |
| MLcam | Mauna Loa | Summit | No |
| MTcam | Mauna Loa | Summit | **Yes** |
| MKcam | Mauna Loa | Northeast Rift Zone | No |
| MK2cam | Mauna Loa | Northeast Rift Zone | No |
| M2cam | Mauna Loa | Southwest Rift Zone | No |
| M3cam | Mauna Loa | Southwest Rift Zone | No |
| MSPcam | Mauna Loa | Southwest Rift Zone | No |
| MDLcam | Mauna Loa | Southwest Rift Zone | No |

Thermal cameras (`F1cam`, `MSTcam`, `MTcam`) use FLIR-style thermal imaging and continue to image volcanic activity through gas plumes.

---

## Installation

No external dependencies. The client uses only Python stdlib (`urllib`, `json`, `re`).

```bash
# Python 3.8+
python3 usgs_volcanocams_client.py
```

---

## Quick Usage

```python
from usgs_volcanocams_client import USGSVolcanoCamClient

client = USGSVolcanoCamClient()

# ---- Volcano status ----

# All US volcanoes with current alert levels
volcanoes = client.get_us_volcanoes()

# Status for Kilauea (vnum) or by USGS code
status = client.get_volcano_status("332010")   # vnum
status = client.get_volcano_status("hi3")       # volcanoCd
print(status["alertLevel"], status["colorCode"])

# Currently elevated volcanoes (HANS Public API)
elevated = client.get_elevated_volcanoes()

# All US volcanoes as GeoJSON
geojson = client.get_volcanoes_geojson()

# Bounding box GeoJSON (Hawaii)
gj = client.volcano.get_geojson_region(lat1=18, lat2=22, lon1=-156, lon2=-154)

# ---- HVO cameras (Hawaii) ----

# List all HVO cameras
hvo_cams = client.hvo.list_cameras()
# Thermal only
thermal = client.hvo.list_cameras(thermal_only=True)
# Kilauea only
kil_cams = client.hvo.list_cameras(volcano="Kilauea")

# Download current image
jpeg = client.hvo.get_image("K2cam")
with open("k2cam.jpg", "wb") as f:
    f.write(jpeg)

# Check last-updated timestamp
meta = client.hvo.get_metadata("K2cam")
print(meta["datetime_hst"])   # "2026-03-27 06:20:08 (HST)"
print(meta["image_url"])

# ---- AVO cameras (Alaska) ----

# All 386 cameras
cams = client.avo.list_cameras()

# Cameras for a specific volcano
cleveland_cams = client.avo.cameras_for_volcano("Cleveland")
shishaldin_cams = client.avo.get_volcano_webcams("ak252")

# Download current image
jpeg = client.avo.get_current_image("augustine")
jpeg_thumb = client.avo.get_current_image("augustine", size="thumb")

# Current image URL (no download)
url = client.avo.current_image_url("augustine")
print(url)   # https://avo.alaska.edu/ashcam-api/images/augustine/current.jpg

# Images from last 7 days (up to 50)
images = client.avo.list_images("augustine", days=7, limit=50)
for img in images:
    print(img["imageDate"], img["imageUrl"])

# Images in a Unix timestamp range
import time
start = int(time.time()) - 7 * 86400
end = int(time.time())
images = client.avo.list_images_range("redoubt", start_ts=start, end_ts=end, limit=200)

# Images showing volcanic activity (interestingCode=V)
hot = client.avo.get_interesting_images(days=30)

# Most recent 20 images across all AVO cameras
recent = client.avo.get_recent_images(limit=20)

# Historical archive query (up to 5000 results)
archived = client.avo.list_archive_images("augustine", start_ts=start, end_ts=end, limit=100)

# GeoJSON for AVO cameras in a bounding box
geojson = client.avo.get_geojson(lat1=55, lat2=60, lon1=-165, lon2=-155)

# ---- CVO cameras (Cascades) ----

# Cameras for a volcano
rainier = client.cvo.cameras_for_volcano("Mount Rainier")
msh = client.cvo.cameras_for_volcano("Mount St. Helens")

# Download current image via VolcView API
jpeg = client.cvo.get_current_image("rainier-mountain")

# Johnston Ridge Observatory legacy public webcam (no history available)
jpeg = client.cvo.get_legacy_jro_image()

# ---- YVO cameras (Yellowstone) ----

jpeg = client.yvo.get_current_image("ys-bbsn")   # Black Diamond Pool

# History (via VolcView)
imgs = client.yvo.list_images("yvoBiscuit", days=7, limit=50)

# ---- Cross-observatory shorthand ----

jpeg = client.get_camera_image("HVO", "B1cam")
jpeg = client.get_camera_image("AVO", "augustine", size="medium")
jpeg = client.get_camera_image("CVO", "msh-edifice")
jpeg = client.get_camera_image("YVO", "ys-bbsn")

images = client.get_historical_images("CVO", "msh-dome", days=1, limit=24)

# ---- HANS notices ----

# Recent notices (last 7 days) from all observatories
alerts = client.get_recent_alerts(days=7)

# Specific observatory
hvo_alerts = client.hans.get_recent_notices_by_obs(obs="hvo", days=7)
avo_alerts = client.hans.get_recent_notices_by_obs(obs="avo", days=7)

# Get a specific notice
notice = client.hans.get_notice("DOI-USGS-HVO-2026-03-26T18:04:33+00:00")
notice_json = client.hans.get_notice_formatted("DOI-USGS-HVO-2026-03-26T18:04:33+00:00", fmt="json")

# Search historical notices
results = client.hans.search_notices(
    obs_abbr="hvo",
    notice_type_cd="WU",      # Weekly Update
    start_unixtime=1700000000,
    search_text="eruption",
)

# Count before searching
count = client.hans.search_preflight(obs_abbr="avo", notice_type_cd="DU")

# VONAs (aviation notices)
vonas = client.hans.get_vonas_last_year()

# ---- Volcano messages (Kilauea) ----

msg = client.msg.get_newest("332010")
print(msg["message"])
recent_msgs = client.msg.get_recent("332010", limit=5)

# ---- Monitoring station plots ----

plots = client.volcano.get_station_plots("332010")
for station in plots["stations"][:3]:
    for plot in station["plots"]:
        print(f"  {plot['plot_label']:30s}  {plot['plot_url']}")

# ---- Observatories ----

all_obs = client.obs.get_all()
hvo_info = client.obs.get_one("HVO")
```

---

## Advanced: Building and Parsing Image URLs

```python
from usgs_volcanocams_client import AVOClient, image_url_to_datetime
from datetime import datetime, timezone

# Build a URL for a known time
client = AVOClient()
dt = datetime(2026, 3, 27, 17, 20, 0, tzinfo=timezone.utc)
url = client.build_image_url(client._base, "augustine", dt)
# → https://avo.alaska.edu/ashcam-api/images/augustine/2026/85/augustine-20260327T172000Z.jpg

# Parse a URL back to a datetime
dt = image_url_to_datetime(url)
print(dt)   # 2026-03-27 17:20:00+00:00

# Parse components
parts = client.parse_image_url(url)
# → {'webcam_code': 'augustine', 'year': '2026', 'day_of_year': '85', 'timestamp_str': '20260327T172000Z'}
```

---

## Data Freshness

| System | Typical update interval |
|--------|------------------------|
| HVO `M.jpg` | Every 1–10 min (camera-dependent) |
| HVO `js.js` timestamp | Updated with each new frame |
| AVO `current.jpg` | Every 10–30 min (FAA cams may differ) |
| VolcView `current.jpg` | Mirrors AVO with slight delay |
| CVO JRO legacy JPEG | ~10 min |
| VHP status (`vhpstatus`) | Near-real-time as notices are issued |
| AVO image archive | New image appended ~hourly per camera |
| HANS notices | As issued by USGS scientists |

---

## Complete URL Summary

| URL | Description |
|-----|-------------|
| `https://volcanoes.usgs.gov/vsc/api/` | VSC API documentation index |
| `https://volcanoes.usgs.gov/vsc/api/volcanoApi/volcanoesUS` | All US volcanoes |
| `https://volcanoes.usgs.gov/vsc/api/volcanoApi/vhpstatus` | Status for all volcanoes |
| `https://volcanoes.usgs.gov/vsc/api/volcanoApi/vhpstatus/{id}` | Status for one volcano |
| `https://volcanoes.usgs.gov/vsc/api/volcanoApi/geojson` | US volcanoes GeoJSON |
| `https://volcanoes.usgs.gov/vsc/api/volcanoApi/elevated` | Elevated activity |
| `https://volcanoes.usgs.gov/vsc/api/volcanoApi/volcano?vnum={v}` | Single volcano metadata |
| `https://volcanoes.usgs.gov/vsc/api/volcanoApi/volcanoStationPlots/{v}` | Monitoring plots |
| `https://volcanoes.usgs.gov/vsc/api/observatoryApi/observatories` | All observatories |
| `https://volcanoes.usgs.gov/vsc/api/hansApi/vonas/{days}` | Recent VONAs |
| `https://volcanoes.usgs.gov/vsc/api/hansApi/newest` | Newest notice per observatory |
| `https://volcanoes.usgs.gov/vsc/api/volcanoMessageApi/volcanoNewest/332010` | Kilauea message |
| `https://volcanoes.usgs.gov/hans-public/api/` | HANS Public API index |
| `https://volcanoes.usgs.gov/hans-public/api/volcano/getElevatedVolcanoes` | Elevated volcanoes |
| `https://volcanoes.usgs.gov/hans-public/api/volcano/getMonitoredVolcanoes` | Monitored volcanoes |
| `https://volcanoes.usgs.gov/hans-public/api/notice/getRecentNotices` | Recent notices |
| `https://volcanoes.usgs.gov/hans-public/api/notice/recent/all/7` | Notices last 7 days |
| `https://volcanoes.usgs.gov/hans-public/api/search/search` | Notice search (POST) |
| `https://volcanoes.usgs.gov/cams/{ID}/images/M.jpg` | HVO current image |
| `https://volcanoes.usgs.gov/cams/{ID}/images/js.js` | HVO timestamp sidecar |
| `https://avo.alaska.edu/ashcam-api/` | AVO Ashcam API docs |
| `https://avo.alaska.edu/ashcam-api/webcamApi/webcams` | All AVO cameras |
| `https://avo.alaska.edu/ashcam-api/images/{CAM}/current.jpg` | AVO current image |
| `https://avo.alaska.edu/ashcam-api/imageApi/webcam/{CAM}/{DAYS}/newestFirst/{LIMIT}` | AVO image history |
| `https://avo.alaska.edu/ashcam-api/imageApi/interesting/{DAYS}` | Volcanic activity images |
| `https://volcview.wr.usgs.gov/ashcam-api/webcamApi/webcams` | CVO/YVO cameras |
| `https://volcview.wr.usgs.gov/ashcam-api/images/webcams/{CAM}/current.jpg` | CVO/YVO current image |
| `https://volcanoes.usgs.gov/vsc/captures/st_helens/jro-webcam.jpg` | CVO JRO legacy cam |
| `https://volcanoes.usgs.gov/images/icons/map/{level}_{code}.png` | Status icon images |

---

## Observatory Abbreviations

| Abbr | Full Name |
|------|-----------|
| AVO | Alaska Volcano Observatory |
| CalVO | California Volcano Observatory |
| CVO | Cascades Volcano Observatory |
| HVO | Hawaiian Volcano Observatory |
| NMI | Northern Mariana Islands |
| YVO | Yellowstone Volcano Observatory |

---

## Notes

- All endpoints are unauthenticated and publicly accessible.
- Respect rate limits; do not exceed ~1 request/second to any single host.
- Station plots endpoint (`volcanoStationPlots`) requests at least 10 minutes between re-queries.
- AVO cameras include many FAA-operated weather cams that happen to view active volcanoes. These are labeled with `organization: "FAA"` and `faaInd: "Y"`.
- `interestingCode: "V"` on AVO images is the fastest machine-readable indicator of new volcanic activity. It is set manually by USGS staff.
- VolcView (`volcview.wr.usgs.gov`) mirrors the AVO database. Its `/images/webcams/{CODE}/` path differs from AVO's `/images/{CODE}/` path.
- The HANS Public API (`hans-public`) is the recommended modern interface. The legacy VSC HANS API (`vsc/api/hansApi`) is also functional.
- The HVO VSC Webcams API (`hvoWebcamsApi`) currently returns empty arrays. Use the legacy `/cams/` system for HVO images.
- Volcano numbers (`vnum`) are assigned by the Smithsonian Institution's Global Volcanism Program. USGS also uses its own `volcanoCd` codes.
- USGS streams Kilauea summit webcams live on YouTube: `https://www.youtube.com/@usgs/streams`
