# FAA WeatherCams Python Client

Reverse-engineered client for the [FAA WeatherCams](https://weathercams.faa.gov) system — the U.S. Federal Aviation Administration's network of ~922 aviation weather camera sites, heavily concentrated in Alaska (252 sites).

## Discovery Method

The API was reverse-engineered by:
1. Fetching the React SPA HTML from `https://weathercams.faa.gov/`
2. Downloading and statically analyzing the minified JavaScript bundle (`bundle.75ff6b6298d6cc4d6af6.js`, ~2 MB)
3. Extracting URL construction patterns, `apiEndpoint` constants, CDN domain strings, and fetch call patterns
4. Live-testing each discovered endpoint to validate behavior and document response schemas

No browser automation was needed — the full API surface is discoverable through static bundle analysis.

---

## Authentication

The production environment has `authEnabled: false` (confirmed in the bundle's prod config block). However, the server enforces an **HTTP Referer check**: requests without a `Referer: https://weathercams.faa.gov/` header receive a `401 Unauthorized` response.

**Required headers on every request:**
```
Referer: https://weathercams.faa.gov/
Origin: https://weathercams.faa.gov
Accept: application/json
User-Agent: <any non-empty value>
```

The client sets these automatically.

---

## Installation

```bash
pip install requests
```

Copy `faa_weathercams_client.py` to your project. No other dependencies needed.

---

## Quick Start

```python
from faa_weathercams_client import FAAWeatherCamsClient

client = FAAWeatherCamsClient()

# All 922 camera sites
sites = client.list_sites()
print(f"Total sites: {len(sites)}")

# Alaska only (252 sites)
ak_sites = client.get_alaska_camera_sites()

# Current conditions + METAR/TAF/NOTAM for Kotzebue, AK
conditions = client.get_current_conditions("PAOT")
print(conditions["metar_raw"])
# METAR PAOT 271753Z 12012KT 4SM -SN OVC037 M12/M14 A3041 ...

# Most recent image for each camera at site 217
images = client.get_site_images(217)
for img in images[:3]:
    print(img["imageUri"])
# https://images.wcams-static.faa.gov/webimages/217/27/10722-1774634436724.jpg
```

---

## API Reference

### Base URL

```
https://weathercams.faa.gov/api
```

All endpoints return JSON:
```json
{
  "success": true,
  "count": 922,
  "payload": [ ... ]
}
```

---

### Camera Sites

#### `GET /api/sites`

List all camera sites (922 total as of March 2026).

**Optional query parameter:** `bounds={S},{W}|{N},{E}` — filter by bounding box.

**Response fields per site:**
| Field | Type | Description |
|-------|------|-------------|
| `siteId` | int | Unique numeric site ID |
| `siteName` | str | Human-readable site name |
| `siteIdentifier` | str | FAA facility identifier (e.g. `"OLB"`) |
| `icao` | str\|null | ICAO airport code if applicable (e.g. `"PAOT"`) |
| `latitude` | float | WGS84 decimal degrees |
| `longitude` | float | WGS84 decimal degrees |
| `elevation` | int | Elevation in meters MSL |
| `state` | str | Two-letter US state code (e.g. `"AK"`) |
| `country` | str | Country code (e.g. `"US"`) |
| `timeZone` | str | IANA timezone (e.g. `"America/Anchorage"`) |
| `siteInMaintenance` | bool | Currently offline for maintenance |
| `siteActive` | bool | Site is operational |
| `thirdParty` | bool | Operated by a third party (not FAA) |
| `validated` | bool | Site has been validated |
| `wxsrc` | int | Weather source type (1=METAR, 3=advisory) |
| `displayVeia` | bool | VEIA visibility estimation enabled |
| `cameras` | list | List of camera objects at this site |

**Camera object fields:**
| Field | Type | Description |
|-------|------|-------------|
| `cameraId` | int | Unique numeric camera ID |
| `cameraName` | str | e.g. `"Camera 1"` |
| `cameraDirection` | str | Cardinal/intercardinal direction (e.g. `"NorthEast"`) |
| `cameraBearing` | int | Magnetic bearing in degrees |
| `cameraLastSuccess` | str | ISO 8601 UTC timestamp of last successful image capture |
| `cameraInMaintenance` | bool | Camera offline for maintenance |
| `cameraOutOfOrder` | bool | Camera has failed |
| `displayOrder` | int | Display sort order |
| `enableVeia` | bool | VEIA processing enabled for this camera |
| `veiaProcessType` | int | VEIA algorithm variant |
| `mapWedgeAngle` | int | Map display field-of-view angle |

#### `GET /api/sites/{siteId}`

Single site by numeric ID. Returns the same schema as above but for one site.

---

### Camera Listing

#### `GET /api/cameras`

List all cameras across all sites (3337 total). Same schema as the camera objects in `/sites`.

#### `GET /api/cameras/{cameraId}`

Single camera by numeric ID.

---

### Camera Images

#### `GET /api/cameras/{cameraId}/images/last/{n}`

Last `n` images captured by a camera.

**Response payload:** list of image objects:
| Field | Type | Description |
|-------|------|-------------|
| `cameraId` | int | Camera ID |
| `imageFilename` | str | Filename (e.g. `10415-1774629011348.jpg`) |
| `imageUri` | str | Full CDN URL |
| `imageDatetime` | str | ISO 8601 UTC capture time |

Cameras typically capture at ~5-minute intervals. Requesting `n=96` returns ~8 hours of history.

#### `GET /api/cameras/{cameraId}/images/clearday`

The manually-curated clear-day reference image for a camera.

**Response payload:**
```json
{
  "cameraId": 10415,
  "imageUri": "https://cleardays.wcams-static.faa.gov/10415-clearday.jpg",
  "imageFilename": "10415-clearday.jpg"
}
```

#### `GET /api/sites/{siteId}/images`

Most-recent images for all cameras at a site, sorted by capture time (newest first).

**Optional parameters:**
| Parameter | Format | Description |
|-----------|--------|-------------|
| `startDate` | `YYYY-MM-DDTHH:MM:SSZ` | Earliest image datetime |
| `endDate` | `YYYY-MM-DDTHH:MM:SSZ` | Latest image datetime |

#### `GET /api/sites/{siteId}/images/download`

Download all site images for a time range as a ZIP archive.

ZIP structure:
```
{siteName}/{YYYY-MM-DD}/{cameraId}/{HH-MM-SS.mmmZ}.jpg
```

Same `startDate`/`endDate` parameters apply.

---

### Site Alerts

#### `GET /api/site-alerts`

All active maintenance and upgrade notifications.

| Field | Type | Description |
|-------|------|-------------|
| `siteId` | int | Affected site |
| `title` | str | Alert title |
| `alert` | str | Alert body (may contain HTML) |
| `effectiveDate` | str | ISO 8601 UTC |
| `expiredDate` | str\|null | Null = no expiry |

---

### Panoramic Cameras (360°)

4 sites have 360-degree panoramic cameras as of March 2026.

#### `GET /api/panoramas`

List all panorama-capable sites.

| Field | Type | Description |
|-------|------|-------------|
| `panoramaSiteId` | int | Panorama site ID (distinct from `siteId`) |
| `siteId` | int | FAA WeatherCam site ID |
| `northOffset` | int | North offset degrees for orientation |
| `defaultYaw` | int | Default viewer yaw angle |
| `defaultHfov` | int | Default horizontal field of view |
| `maxZoomLevel` | int | Maximum cube face zoom levels |
| `hotspots` | list | Annotated bearing/distance markers |
| `cubeResolution` | int | Cube face resolution in pixels |
| `clearDayImage` | dict | Clear-day pyramid tile URLs and timestamp |

#### `GET /api/panoramas/{panoramaSiteId}`

Single panorama site configuration.

#### `GET /api/panoramas/{panoramaSiteId}/images/last/{n}`

Last `n` panoramic images.

Each image includes:
| Field | Type | Description |
|-------|------|-------------|
| `imageId` | str (UUID) | Unique image ID |
| `imageType` | str | Always `"equirectangular"` for live images |
| `timestamp` | str | ISO 8601 UTC |
| `imageUris.thumbnail` | str | Thumbnail JPEG |
| `imageUris.small` | str | Small WebP |
| `imageUris.medium` | str | Medium WebP |
| `resourceUris.src` | list[str] | 4 equirectangular tile JPEGs (indices 0–3) |

---

### Weather Summary

#### `GET /api/summary?stationId={icao}` or `GET /api/summary?siteId={siteId}`

The most comprehensive endpoint — returns everything for a location.

**Response top-level keys:**

| Key | Type | Description |
|-----|------|-------------|
| `site` | dict | Site metadata + cameras with current images + VEIA visibilities |
| `airport` | dict | Airport facility info + chart supplement docs |
| `rtmaReports` | list | Real-Time Mesoscale Analysis temperature/altimeter corrections |
| `station` | dict | METAR station metadata and service status |
| `metars` | list | Recent METAR observations (newest first) |
| `notams` | list | Active NOTAMs |
| `tafs` | list | Active TAF forecasts |
| `rco` | dict | Remote Communication Outlet frequencies |
| `aircraftReports` | list | Recent PIREPs near the location |
| `timeZoneId` | str | IANA timezone string |

**METAR fields:**
| Field | Description |
|-------|-------------|
| `rawText` | Raw METAR string |
| `flightCategory` | `"VFR"` / `"MVFR"` / `"IFR"` / `"LIFR"` |
| `ceilingFtAgl` | Ceiling in feet AGL |
| `visibilityStatuteMiles` | Visibility in statute miles |
| `tempC` | Temperature °C |
| `dewpointC` | Dewpoint °C |
| `windDirDegrees` | Wind direction °M |
| `windSpeedKnots` | Wind speed kt |
| `windGustKnots` | Wind gust kt (null if calm) |
| `altimInHg` | Altimeter setting inHg |
| `wxString` | Present weather codes (e.g. `"-SN"`) |
| `skyCondition` | List of `{skyCover, cloudBaseFtAgl}` |
| `parsed` | Human-readable version of key fields |

**VEIA Visibility fields** (from `site.visibilities`):
| Field | Description |
|-------|-------------|
| `visibilityStatuteMi` | AI-estimated visibility in SM |
| `confidence` | Estimation confidence 0–100 |
| `camerasUpdated` | Number of cameras used |
| `processedTime` | UTC when VEIA ran |
| `skyCondition.skyCover` | `"CLR"` / `"FEW"` / `"SCT"` / `"BKN"` / `"OVC"` |
| `skyCondition.cloudPercentage` | Sky cover 0–100% |
| `skyCondition.skyCoverOktas` | Oktas 0–8 |

**RTMA Report fields:**
| Field | Description |
|-------|-------------|
| `twoMeterTempC` | 2-meter model temperature °C |
| `tempDifferenceC` | Difference from station obs |
| `tempMitigationC` | Recommended cold-temp altimetry correction °C |
| `altimInHg` | Model altimeter inHg |
| `altimMitigationInHg` | Altimeter correction inHg |
| `mitigatedTwoMeterTempC` | Corrected temperature °C |

---

### METAR / TAF

#### `GET /api/metars/stations/{stationId}`

Recent METAR observations for an ICAO station (typically last 3–5 reports).

#### `GET /api/tafs/stations/{stationId}`

Active TAF forecasts for an ICAO station.

TAF `forecast` array fields:
| Field | Description |
|-------|-------------|
| `fcstTimeFrom` | Period start (ISO 8601 UTC) |
| `fcstTimeTo` | Period end |
| `changeIndicator` | `"FM"` / `"TEMPO"` / `"BECMG"` / `"PROB30"` |
| `windDirDegrees` | Wind direction °M |
| `windSpeedKt` | Wind speed kt |
| `visibilityStatuteMi` | Visibility SM |
| `ceilingFtAgl` | Ceiling ft AGL |
| `flightCategory` | `"VFR"` etc. |
| `wxString` | Weather codes |
| `skyCondition` | List of sky layers |

#### `GET /api/stations/{stationId}`

Station metadata:
| Field | Description |
|-------|-------------|
| `stationId` | ICAO identifier |
| `faaId` | FAA 3-letter ID |
| `icaoId` | ICAO 4-letter ID |
| `iataId` | IATA 3-letter ID |
| `wmoId` | WMO station number |
| `siteType` | `["METAR"]` / `["METAR","TAF"]` |
| `facilityType` | `"ASOS"` / `"AWOS"` etc. |
| `status.description` | `"In Service"` etc. |

---

### Map Layer Endpoints (Bounding Box)

All take `bounds={S},{W}|{N},{E}` as a query parameter.

#### `GET /api/locations?bounds=...`

Combined location data for the map. Each location has a `data` array with typed entries:
- `type: "airport"` — airport facility info
- `type: "cameraSite"` — WeatherCam site summary
- `type: "station"` — METAR station metadata
- `type: "rco"` — RCO frequencies
- `type: "metar"` — Latest METAR flight category

#### `GET /api/advisory-weather?bounds=...`

Non-certified sensor observations (wind, temp, humidity, rain) from camera sites with embedded weather stations. Each observation includes a prominent disclaimer: *"This is an advisory weather source and is not certified."*

#### `GET /api/aircraft-reports?bounds=...`

PIREPs in the bounding box. Returns full PIREP data including turbulence, icing, and sky condition reports.

#### `GET /api/airsigmets?bounds=...`

Active AIRMETs and SIGMETs.

#### `GET /api/gairmets?bounds=...`

Active G-AIRMETs (graphical AIRMETs).

#### `GET /api/rcos?bounds=...`

Remote Communication Outlets with their VHF/UHF frequencies.

#### `GET /api/tfrs?bounds=...`

Active Temporary Flight Restrictions.

---

## CDN Domains & Image URL Patterns

### Camera Images

CDN: `https://images.wcams-static.faa.gov` (CloudFront → S3, no auth required)

```
/webimages/{siteId}/{dayOfMonth}/{cameraId}-{unix_ms}.jpg
```

Example: `https://images.wcams-static.faa.gov/webimages/217/27/10724-1774634135008.jpg`

- `siteId` — numeric FAA site ID
- `dayOfMonth` — UTC day of month (1–31)
- `cameraId` — numeric camera ID
- `unix_ms` — Unix timestamp in milliseconds (matches capture datetime)

### Clear-Day Reference Images

CDN: `https://cleardays.wcams-static.faa.gov` (CloudFront → S3, no auth required)

```
/{cameraId}-clearday.jpg
```

### Panorama Images (Live)

CDN: `https://images.wcams-static.faa.gov`

```
/pano/{siteId}/{unix_ms}/thumbnail.jpg     # JPEG thumbnail
/pano/{siteId}/{unix_ms}/small.webp        # Small WebP
/pano/{siteId}/{unix_ms}/medium.webp       # Medium WebP
/pano/{siteId}/{unix_ms}/0.jpg             # Equirectangular tile 0
/pano/{siteId}/{unix_ms}/1.jpg             # Equirectangular tile 1
/pano/{siteId}/{unix_ms}/2.jpg             # Equirectangular tile 2
/pano/{siteId}/{unix_ms}/3.jpg             # Equirectangular tile 3
```

### Panorama Clear-Day Images (Pyramid Tiles)

CDN: `https://cleardays.wcams-static.faa.gov`

```
/pano/{siteId}/thumbnail.jpg              # Thumbnail
/pano/{siteId}/pyramid                    # Pyramid tile base path
/pano/{siteId}/pyramid/{z}/{x}/{y}.jpg   # Individual tiles
```

### Aviation Chart Tiles (IFR/VFR)

CDN: `https://aeronav.wcams-static.faa.gov` (requires authenticated session; accessed via the web app)

Chart types discovered in the bundle:
- IFR Enroute Low: `/ifr-enroute-low/{chartName}/{z}/{x}/{y}.png`
- IFR Enroute High: `/ifr-enroute-high/{chartName}/{z}/{x}/{y}.png`
- VFR Sectional: `/vfr-sectional/{chartName}/{z}/{x}/{y}.png`

Alaska-specific charts include: Anchorage, Fairbanks, Nome, Juneau, Ketchikan, Kodiak, McGrath, Bethel, Cold Bay, Dutch Harbor, Seward, Point Barrow, Cape Lisburne, Western Aleutian Islands, and IFR Enroute charts ELAK1–ELAK4 and EHAK1–EHAK2.

---

## Bounds Format

Bounding boxes use the format `{S},{W}|{N},{E}` (south,west pipe north,east).

```python
from faa_weathercams_client import FAAWeatherCamsClient

# Entire Alaska
bounds = FAAWeatherCamsClient.alaska_bounds()   # "51.2,-179.9|71.5,-129.0"

# Custom bounding box (southwest AK / Kodiak area)
bounds = FAAWeatherCamsClient.make_bounds(south=55.0, west=-160.0, north=62.0, east=-148.0)

# Use in any map endpoint
wx = client.get_advisory_weather(bounds)
```

---

## Alaska Focus

Alaska is the primary use case for WeatherCams — 252 of 922 sites (27%) are in Alaska. Alaska stations have ICAO identifiers starting with `PA` (e.g. `PAOT`, `PAFA`, `PANC`, `PAJN`).

Highly active Alaska sites:
| Site ID | Name | ICAO | Notes |
|---------|------|------|-------|
| 217 | Kotzebue | PAOT | ASOS, TAF available |
| 264 | Sitka | PАСY | Has panoramic camera |
| 102 | Juneau | PAJN | Has panoramic camera |
| 535 | Homer | PAHO | Has panoramic camera |
| 550 | (TBD) | - | Has panoramic camera |
| 142 | Old Harbor | OLB | Advisory WX only |

---

## Response Envelope

All API endpoints return a consistent JSON envelope:

```json
{
  "success": true,
  "count": 922,
  "payload": [ ... ]
}
```

Error responses:
```json
{
  "success": false,
  "payload": null,
  "error": {
    "code": 401,
    "message": "Unauthorized"
  }
}
```

Common error codes:
- `401` — Missing or invalid Referer header
- `404` — Endpoint or resource not found
- `500` — Internal server error (often a malformed query parameter)

---

## Usage Examples

### Get all Alaska sites with current METAR flight category

```python
client = FAAWeatherCamsClient()
summary_stations = ["PANC", "PAFA", "PAJN", "PAOT", "PAKN", "PAHN", "PAOM"]

for icao in summary_stations:
    try:
        conds = client.get_current_conditions(icao)
        print(f"{icao}: {conds['flight_category']} | {conds['metar_raw'][:60]}")
    except Exception as e:
        print(f"{icao}: error - {e}")
```

### Download and save the latest image from each camera at a site

```python
import requests

client = FAAWeatherCamsClient()
site_id = 217  # Kotzebue

images = client.get_latest_image_for_site(site_id)
for img in images:
    url = img["imageUri"]
    filename = f"cam_{img['cameraId']}_{img['cameraDirection']}.jpg"
    data = requests.get(url, timeout=30).content
    with open(filename, "wb") as f:
        f.write(data)
    print(f"Saved {filename}")
```

### Get advisory weather readings across Alaska

```python
client = FAAWeatherCamsClient()
ak_wx = client.get_advisory_weather(client.alaska_bounds())

# Filter sites below -20°F
cold_sites = [
    obs for obs in ak_wx
    if obs.get("tempF") is not None and obs["tempF"] < -20
]
print(f"Sites below -20°F: {len(cold_sites)}")
for obs in sorted(cold_sites, key=lambda x: x["tempF"])[:5]:
    print(f"  Site {obs['siteId']}: {obs['tempF']}°F, wind {obs['windSpeedKnots']}kt")
```

### Download a ZIP archive of site images

```python
from datetime import datetime, timezone
import zipfile, io

client = FAAWeatherCamsClient()

start = datetime(2026, 3, 27, 0, 0, 0, tzinfo=timezone.utc)
end   = datetime(2026, 3, 27, 6, 0, 0, tzinfo=timezone.utc)

zf = client.extract_site_images_zip(142, start_date=start, end_date=end)
print("Files in archive:")
for name in zf.namelist()[:10]:
    print(f"  {name}")
```

### Get panorama images for a 360-camera site

```python
client = FAAWeatherCamsClient()

# List panorama sites and fetch last 3 images for the first one
panos = client.list_panoramas()
latest = client.get_panorama_images_last(panos[0]["panoramaSiteId"], n=3)

for img in latest:
    print(f"Timestamp: {img['timestamp']}")
    print(f"  Thumbnail: {img['imageUris']['thumbnail']}")
    print(f"  Tiles:     {img['resourceUris']['src'][:2]} ...")
```

### Get PIREPs over Alaska

```python
client = FAAWeatherCamsClient()
pireps = client.get_aircraft_reports(client.alaska_bounds())

for pirep in pireps:
    turb = pirep.get("turbulenceCondition")
    icing = pirep.get("icingCondition")
    print(
        f"FL{pirep.get('altitudeFtMsl',0)//100:03d} "
        f"({pirep['latitude']:.1f},{pirep['longitude']:.1f}) "
        f"turb={turb[0]['turbulenceIntensity'] if turb else 'NEG'} "
        f"ice={icing[0]['icingIntensity'] if icing else 'NEG'}"
    )
```

---

## Rate Limiting

No rate limiting was observed during testing. The API is a public government service. Please be a responsible consumer — avoid polling faster than the camera update interval (~5 minutes). The `cameraLastSuccess` field tells you when a camera last captured an image.

---

## Notes

- The FAA WeatherCams server runs on Node.js behind Akamai CDN
- Camera images expire from the CDN after approximately 33 days (`x-amz-expiration` header confirms this)
- The VEIA (Visibility Estimation from Image Analysis) system uses computer vision to estimate visibility from camera images — it is explicitly marked as advisory/non-certified
- Sites with `wxsrc: 1` have official METAR data; `wxsrc: 3` have only advisory sensor data
- The `magVariation` field provides magnetic declination for the site, updated monthly
- Contact for FAA WeatherCams: `9-AJO-WCAM-IT@faa.gov`
