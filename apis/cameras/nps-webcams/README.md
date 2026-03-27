# NPS Webcams & Air Quality Cameras — Reverse-Engineered API Client

Complete Python client covering **two distinct NPS webcam systems**:

| System | Webcams | Parks | Auth | Notes |
|--------|---------|-------|------|-------|
| NPS Developer API | 290 total | All 474 NPS units | DEMO_KEY (free) | Streaming cameras, full park metadata |
| NPS ARD Air Quality Network | 22 scientific cameras | 20 major parks | None | 15-min updates, archive to 2005 |

---

## System 1: NPS Developer API

### Overview

The public NPS Developer API at `developer.nps.gov` serves the complete catalogue of
290 webcams across all NPS units — from Brooks Falls Bearcams in Katmai to Old Faithful
in Yellowstone to El Capitan in Yosemite.  It also provides rich park metadata including
hours, fees, addresses, images, contacts, and coordinates.

**No registration required** for the `DEMO_KEY` (~1,000 req/hour).  Free API key at
https://www.nps.gov/subjects/digital/nps-data-api.htm for higher limits.

### Base URL

```
https://developer.nps.gov/api/v1/
```

### Authentication

Pass your key as a query parameter or HTTP header:

```
?api_key=DEMO_KEY
X-Api-Key: DEMO_KEY
```

### Endpoints

| Path | Method | Description |
|------|--------|-------------|
| `/webcams` | GET | List webcams with filtering and pagination |
| `/parks` | GET | Park metadata (description, hours, fees, images, GPS) |
| `/alerts` | GET | Current closures and hazards |
| `/events` | GET | Scheduled park events |
| `/newsreleases` | GET | NPS news releases |
| `/articles` | GET | In-depth articles |
| `/places` | GET | Specific locations within parks |
| `/amenities` | GET | Available amenities by park |

### Webcams Endpoint

```
GET https://developer.nps.gov/api/v1/webcams
```

**Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `api_key` | string | Required. Use `DEMO_KEY` or your registered key |
| `limit` | int | Results per page (default 50, up to 500) |
| `start` | int | Pagination offset (0-indexed) |
| `parkCode` | string | 4-letter code or comma-separated list, e.g. `katm,yell` |
| `q` | string | Full-text search, e.g. `bears`, `geyser`, `air quality` |

**Response shape:**

```json
{
  "total": "290",
  "limit": "50",
  "start": "0",
  "data": [
    {
      "id":          "D32F071A-B8F7-08A4-65F765E8BB714DCF",
      "url":         "https://www.nps.gov/media/webcam/view.htm?id=D32F071A-...",
      "title":       "Brooks Falls Bearcam",
      "description": "Check out a view of Brooks Falls, an iconic bear-viewing area...",
      "images": [
        {
          "url":     "https://www.nps.gov/common/uploads/cropped_image/CCBB1534-BD22-5A82-89A3B23B44CF1C3C.jpg",
          "altText": "A large grizzly bear stands in a rushing river.",
          "title":   "",
          "caption": "",
          "credit":  ""
        }
      ],
      "relatedParks": [
        {
          "parkCode":    "katm",
          "fullName":    "Katmai National Park & Preserve",
          "url":         "https://www.nps.gov/katm/index.htm",
          "designation": "National Park & Preserve",
          "states":      "AK"
        }
      ],
      "status":        "Active",
      "statusMessage": "",
      "isStreaming":   true,
      "tags":          ["wildlife", "bears", "grizzly", "salmon", "waterfall"],
      "latitude":      null,
      "longitude":     null,
      "geometryPoiId": null,
      "credit":        ""
    }
  ]
}
```

### CDN Image URL Patterns

Webcam preview/thumbnail images are served from:

```
https://www.nps.gov/common/uploads/webcam/{UUID}.jpg
https://www.nps.gov/common/uploads/cropped_image/{UUID}.jpg
```

The UUID in the path is the image's own UUID, not the webcam ID.

**Note:** Only ~3% of the 290 webcams have preview images in the `images` array.
The remaining cameras serve their live/refreshing feed through the view page:

```
https://www.nps.gov/media/webcam/view.htm?id={webcam-id}
```

### Known Streaming Webcams (isStreaming: true)

As of March 2026:

| Title | Park | ID |
|-------|------|----|
| Brooks Falls Bearcam | Katmai | `D32F071A-B8F7-08A4-65F765E8BB714DCF` |
| Dumpling Mountain Cam | Katmai | `D3544467-9A96-0068-4B745F74BE0F93F8` |
| River Watch Cam | Katmai | `D404ED1D-E46F-2D08-8729B2BF39A2CCE9` |
| Naknek River Cam | Katmai | `D3A52BBE-EBA9-6A92-2AADC5935F9D882F` |
| Riffles BearCam (replay) | Katmai | `D3D9F63F-C70C-3004-18867136AB648DFA` |
| Old Faithful Livestream | Yellowstone | `CE843A37-74A2-4408-9176-26A8DCC97294` |
| El Capitan | Yosemite | `B28D5845-C504-BBA5-17748BFF1C6CC716` |
| Yosemite High Sierra / Half Dome | Yosemite | `1148077C-F06F-CD3A-969692F6BC0481AC` |
| Channel Islands Live (1) | Channel Islands | `AF555E5C-BE40-FE91-52E98E0EDD833B68` |
| Channel Islands Live (2) | Channel Islands | `2BB1FF1F-BF6C-9F10-BFAFCCEFC8F0D861` |
| Craig Thomas Discovery & VC | Grand Teton | — |
| San Miguel Island Ranger Station | Channel Islands | — |
| Peregrine Falcon Webcam | Channel Islands | — |
| Hemenway Harbor | Lake Mead | — |

### Parks Endpoint

```
GET https://developer.nps.gov/api/v1/parks
```

**Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `api_key` | string | Required |
| `parkCode` | string | 4-letter code(s) |
| `stateCode` | string | 2-letter state, e.g. `CA`, `AK` |
| `q` | string | Full-text search |
| `fields` | string | Extra fields: `images,addresses,latLong,contacts,operatingHours,activities,topics,entranceFees,entrancePasses` |
| `limit` | int | Results per page |
| `start` | int | Offset |

**Total parks in NPS database: 474**

---

## System 2: NPS Air Quality (ARD) Webcam Network

### Overview

22 scientific visibility monitoring cameras at 20 major national parks.
Run by NPS Air Resources Division.  Images every 15 minutes; air quality
data (ozone, PM2.5, SO2, meteorology) updated hourly.  Historical archive
back to **October 18, 2005**.

**No API key or registration required.**

### ARD Webcam Park Inventory

| Code | Park | State | Type |
|------|------|-------|------|
| `acad` | Acadia National Park | Maine | single |
| `bibe` | Big Bend National Park | Texas | single |
| `brda` | Bryce Canyon National Park | Utah | **dual** |
| `dena` | Denali National Park | Alaska | single |
| `dino` | Dinosaur National Monument | CO/UT | single |
| `grca` | Grand Canyon National Park | Arizona | **dual** |
| `grte` | Grand Teton National Park | Wyoming | single |
| `grcd` | GSMNP – Kuwohi | TN/NC | single |
| `grsm` | GSMNP – Look Rock | TN/NC | single |
| `grpk` | GSMNP – Purchase Knob | TN/NC | single |
| `havo` | Hawaii Volcanoes NP | Hawaii | **HAVO (SO2)** |
| `jotr` | Joshua Tree National Park | California | single |
| `maca` | Mammoth Cave National Park | Kentucky | single |
| `mora` | Mount Rainier National Park | Washington | **dual** |
| `wash` | National Mall and Memorial Parks | DC | **dual** |
| `noca` | North Cascades National Park | Washington | single |
| `olym` | Olympic National Park | Washington | single |
| `pore` | Point Reyes National Seashore | California | single |
| `seki` | Sequoia & Kings Canyon NPs | California | single |
| `shen` | Shenandoah National Park | Virginia | single |
| `thro` | Theodore Roosevelt National Park | North Dakota | single |
| `yose` | Yosemite National Park | California | single |

Park type meanings:
- `single` — one monitoring site (SITE1 in JSON)
- `dual` — two monitoring sites (SITE1 + SITE2)
- `HAVO` — Hawaii Volcanoes special multi-sensor including SO2

### Endpoints Reference

#### Park / Camera Inventory

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/featurecontent/ard/webcams/json/NPSsitelist.txt` | GET | All 22 sites: code, name, state, last image time |
| `/featurecontent/ard/webcams/json/{abbr}json.txt` | GET | Full snapshot: image metadata + current AQ readings |

Add `?uuid={random}` to bypass CDN caching (matches browser JS behaviour).

#### Current Images

| URL Pattern | Size | Notes |
|-------------|------|-------|
| `/featurecontent/ard/webcams/images/{abbr}.jpg` | ~150–250 KB | Standard, updates every 15 min |
| `/featurecontent/ard/webcams/images/{abbr}large.jpg` | ~1.5–2.5 MB | Full-resolution |
| `/features/ard/webcams/supportimages/{abbr}_clear_hazy.jpg` | ~30–40 KB | Reference comparison |
| `/features/ard/webcams/supportimages/{abbr}_terrain_features.jpg` | ~30–60 KB | Annotated landmarks |
| `/features/ard/webcams/supportimages/{abbr}_webcam_map.jpg` | ~50 KB | Camera location map |

Append `?{unix_timestamp_ms}` to force fresh fetch.

#### Archive API

Base: `https://www.nps.gov/airwebcams/`

**GET `/airwebcams/api/GetAvailableDays/{park_code}`**

Returns bitmask structure for all dates with archived images:

```json
{
  "2005": {"10": 2144337920},
  "2006": {"1": 2147483647, "2": 268435455, ...},
  "MinDay": "10/18/2005",
  "MaxDay": "3/27/2026"
}
```

Each value is a 32-bit bitmask; bit N (LSB = day 1) = that day has images.
Use `decode_available_days_bitmask()` to decode.

**POST `/airwebcams/api/Search/Execute`**

Search for images by park and date:

```json
{
  "Operand": {
    "LeftOperand":  {"MatchType": "Exact", "Term": "LocationCode", "Attribute": "yose"},
    "RightOperand": {"CompareType": "=", "Term": "ImageCreateDate", "Attribute": "3/27/2026"},
    "Operator": "AND"
  },
  "ActionFilter": "Search",
  "StatusFilter": "Active",
  "SortTerms": [{"Term": "CreateDate", "Ascending": true}],
  "PageSize": 300,
  "CurrentPage": 1,
  "ResultTerms": ["ImageCreateDate","CustomTextFields","CustomNumberFields","AdditionalMetadata"],
  "SearchID": null,
  "Save": false,
  "CacheResults": false
}
```

Response:
```json
{
  "UnfilteredCount": 96,
  "ResultCount": 96,
  "Results": [
    {
      "Asset": {
        "LocationCode": "yose",
        "LocalTimeString": "3/27/2026 6:00 AM Pacific Daylight Time",
        "TimeOfDay": "day",
        "SolarElevationAngle": 10.3,
        "AssetID": "ad131e43-6b1c-4a5b-8204-026e9f051625",
        "ImageCreateDateTime": "03/27/2026 01:00:00 PM"
      }
    }
  ]
}
```

**GET `/airwebcams/GetAsset/{asset_id}/{size_token}`**

Download archived image (no auth required):

| `size_token` | Approx. size | Notes |
|--------------|-------------|-------|
| `thumbmedium.jpg` | ~1–2 KB | Small thumbnail |
| `thumblarge.jpg` | ~4 KB | Larger thumbnail |
| `full.jpg` | ~1–3 MB | Full resolution |
| `proxy/hires` | ~90 KB | Compressed high-res proxy |

**POST `/airwebcams/api/GetServerTime`**

No request body required. Returns:
```json
{"year": 2026, "month": 3, "day": 27, "hour": 16, "minute": 29}
```

#### Air Quality Timeseries

**GET `/featurecontent/ard/currentdata/json/{abbr}.json`**

30-day hourly AQ data for all monitoring locations:

```json
{
  "name": "Yosemite National Park",
  "dataDate": "3/27/2026 8:00:00 AM PDT",
  "locations": [
    {
      "name": "Turtleback Dome",
      "aqsId": "06-109-2003",
      "ozone": {
        "display": "true",
        "units": "Parts per billion",
        "current": 43.0,
        "current8": 40.0,
        "current8AQI": 41,
        "data": [/* 720 hourly floats, -99.0 = missing */],
        "data8": [/* 720 8h-avg floats */]
      },
      "particulatesPA": {"PM25PA": "3.7", "NOWCASTPA": "3.6"},
      "airTemperature": {...},
      "relativeHumidity": {...},
      "windSpeed": {...},
      "windDirection": {...},
      "barometricPressure": {...},
      "precipitation": {...}
    }
  ]
}
```

- `-99.0` sentinel = missing/unavailable
- 720 values = 30 days × 24 hours, oldest first
- Hawaii Volcanoes has additional `so2` data

**GET `/featurecontent/ard/currentdata/json/{abbr}_smoke.json`**
Gridded PM2.5 + smoke forecast (lat/lon bounding box).

**GET `/featurecontent/ard/currentdata/json/parklist.json`**
Full NPS AQ monitoring park list (more parks than the webcam network).

#### Per-Park Webcam JSON Structure

`GET /featurecontent/ard/webcams/json/{abbr}json.txt`

```json
{
  "name": "Yosemite National Park",
  "state": "California",
  "URL": "https://www.nps.gov/yose/",
  "URLarchives": "https://www.nps.gov/AirWebCams/yose",
  "imagedate": "Updated 03/27/2026 09:15 AM PDT",
  "imagesite": "View from Turtleback Dome",
  "viewdetail": "Looking Southwest",
  "imagefile": "yose.jpg",
  "imagefilelarge": "yoselarge.jpg",
  "imageclearhazy": "yose_clear_hazy.jpg",
  "imagelandmarks": "yose_terrain_features.jpg",
  "imagemapit": "yose_webcam_map.jpg",
  "SITE1": {
    "name": "at Turtleback Dome",
    "URLtimelines": "current-data.htm?site=yose&location=0",
    "OZONE": {
      "display": "true",
      "datadate": "Updated 03/27/2026 09:00 AM PDT",
      "units": "ppb",
      "hourly": "44",
      "average": "41",
      "AQIcolor": "Green",
      "AQItext": "Good",
      "todaymaxhourly": "44",
      "yesterdaymaxhourly": "40"
    },
    "PM25PA": {"display": "true", "PM25PA": "3.7", "NOWCASTPA": "3.6"},
    "AT":  {"hourly": "63", "units": "°F"},
    "RH":  {"hourly": "27", "units": "%"},
    "WS":  {"hourly": "22", "units": "mph"},
    "WD":  {"hourly": "SE", "degrees": "125"},
    "PRECIPLASTHOUR": {"hourly": "0.00", "units": "in."}
  }
}
```

Dual-site parks also have `SITE2`.  HAVO has `SO2` within each site block.

---

## Installation

```bash
pip install requests
```

No other third-party dependencies.

---

## Quick Start

### NPS Developer API (290 webcams)

```python
from nps_webcams_client import NPSWebcamAPIClient

api = NPSWebcamAPIClient()   # DEMO_KEY by default
# api = NPSWebcamAPIClient(api_key="your-key-here")

# Total webcam count
resp = api.list_webcams(limit=1)
print(f"Total: {resp['total']}")  # 290

# All Katmai bear cams
katm = api.list_webcams(park_code="katm")
for cam in katm["data"]:
    print(cam["title"], "streaming:", cam["isStreaming"])

# All streaming webcams (fetches all 290 and filters)
streaming = api.list_streaming_webcams()
for cam in streaming:
    park = cam.get("relatedParks", [{}])[0].get("parkCode", "?")
    print(f"[{park}] {cam['title']} — {cam['url']}")

# Iterate all 290 webcams without worrying about pagination
for cam in api.iter_all_webcams():
    img_url = api.get_webcam_image_url(cam)
    print(cam["id"], cam["title"], img_url or "(no preview)")

# Park metadata
park = api.get_park(park_code="yose")
print(park["fullName"], park["latitude"], park["longitude"])

# Parks in California
for park in api.iter_all_parks(state_code="CA"):
    print(park["parkCode"], park["fullName"])

# GeoJSON of geolocated webcams
geojson = api.get_webcams_geojson(active_only=True)
print(f"{len(geojson['features'])} geolocated webcams")

# Save webcam GeoJSON file
n = api.save_webcams_geojson("nps_webcams.geojson")
print(f"Saved {n} features")
```

### Air Quality Webcam Network (22 cameras)

```python
from nps_webcams_client import NPSAQWebcamsClient

aq = NPSAQWebcamsClient()

# List all parks
parks = aq.list_parks()
for p in parks:
    print(p['abbr'], p['name'])

# Current snapshot for Yosemite
info = aq.get_park_info("yose")
print(info['imagedate'])
print(info['SITE1']['OZONE']['hourly'], "ppb ozone")

# Download current webcam image
img_bytes = aq.get_current_image("yose", size="large")
with open("yose_current.jpg", "wb") as f:
    f.write(img_bytes)

# Support images
for itype in ("clear_hazy", "terrain_features", "webcam_map"):
    url = aq.get_support_image_url("yose", itype)
    print(url)

# Archive: what dates have data?
avail = aq.get_available_days("yose")
print("Archive from:", avail["MinDay"], "to", avail["MaxDay"])

# Archive: search a specific date
results = aq.search_archive("yose", "6/15/2020", daytime_only=True)
for item in results["Results"]:
    asset = item["Asset"]
    print(asset["LocalTimeString"], asset["AssetID"])

# Archive: download one image
asset_id = results["Results"][0]["Asset"]["AssetID"]
img = aq.get_archive_image(asset_id, size="full")
thumb = aq.get_archive_image(asset_id, size="thumbnail_small")

# Archive: iterate and download all daytime images on a date
for local_time, img_bytes in aq.iter_archive_images("yose", "3/27/2026"):
    print(local_time, len(img_bytes), "bytes")

# Archive: bulk download day to directory
paths = aq.download_day_images("yose", "3/27/2026", "/tmp/yose_images/")
print(f"Downloaded {len(paths)} files")

# Air quality timeseries (30-day hourly)
aq_data = aq.get_air_quality_data("yose")
for loc in aq_data["locations"]:
    ozone = loc["ozone"]
    if ozone.get("display") == "true":
        print(f"{loc['name']}: {ozone['current']} ppb ozone, AQI {ozone.get('current8AQI')}")
        # 720 hourly values (sentinel -99.0 = missing)
        series = [x for x in ozone["data"] if x != -99.0]
        print(f"  {len(series)} valid hourly readings over 30 days")

# All parks current readings in one call
readings = aq.get_all_current_readings()
for r in readings:
    print(r['park_code'], r.get('ozone_ppb'), 'ppb ozone', r.get('temperature'), '°F')

# Smoke data
smoke = aq.get_smoke_data("yose")

# Server time
st = aq.get_archive_server_time()
print(f"Server: {st['year']}/{st['month']}/{st['day']} {st['hour']}:{st['minute']:02d}")
```

### Backwards Compatibility

```python
# Original class name still works
from nps_webcams_client import NPSWebcamsClient
client = NPSWebcamsClient()   # same as NPSAQWebcamsClient
```

---

## Archive Bitmask Decoding

```python
from nps_webcams_client import decode_available_days_bitmask

days = decode_available_days_bitmask(2026, 3, 134217727)
# Returns [1, 2, 3, ..., 27]  (bits 0-26 set = days 1-27 have images)
```

---

## AQI Color Scale

| Color | Category | Ozone (ppb) | PM2.5 (µg/m³) |
|-------|----------|-------------|----------------|
| Green | Good | 0–54 | 0–9.0 |
| Yellow | Moderate | 55–70 | 9.1–35.4 |
| Orange | Unhealthy for Sensitive Groups | 71–85 | 35.5–55.4 |
| Red | Unhealthy | 86–105 | 55.5–150.4 |
| Purple | Very Unhealthy | 106+ | 150.5+ |

---

## Notes

### NPS Developer API
- **Rate limits:** DEMO_KEY ~1,000 requests/hour.  Register for a free personal key
  at https://www.nps.gov/subjects/digital/nps-data-api.htm for higher limits.
- **API key in header:** The client sends `X-Api-Key` header — both the query param
  and header are accepted by the API.
- **Image availability:** Only ~3% of the 290 webcams have images in the `images`
  array.  Live feeds are served through `/media/webcam/view.htm?id={id}` pages
  which embed the stream via a CommonSpot CMS loader.
- **Duplicate domain bug:** Some API responses contain malformed image URLs with the
  domain prepended twice (`https://www.nps.govhttps://www.nps.gov/...`).
  `get_webcam_image_url()` automatically corrects this.
- **Streaming:** The `isStreaming: true` flag marks cameras with live or near-live
  video feeds (often powered by partnerships with Explore.org for bear cams).
- **GeoJSON:** Most webcams lack coordinates; air quality cameras (also in the
  Developer API) tend to have GPS coordinates.

### NPS ARD Air Quality Network
- **Update frequency:** Images every 15 minutes; AQ data every hour.
- **Cache busting:** Append `?{timestamp}` to image URLs (the client handles this).
- **Missing data:** `-99.0` and `-99` are sentinel values throughout the API.
- **Time zones:** Times in webcam JSON are in the park's local timezone.
  Archive API stores UTC; `LocalTimeString` converts to local time.
- **Hawaii Volcanoes:** Has SO2 data in addition to PM2.5, reflecting volcanic
  emissions monitoring.
- **Dual-site parks:** `brda`, `grca`, `mora`, `wash` have SITE1 + SITE2 in JSON.
- **Archive depth:** Data from October 18, 2005 onwards (~20+ years).
- **Respecting servers:** No enforced rate limit, but add delays for bulk downloads.
