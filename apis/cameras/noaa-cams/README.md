# NOAA Cameras & Imagery Client

Reverse-engineered Python client for two NOAA real-time imagery systems:

1. **NOAA GOES Satellite CDN** — near real-time ABI imagery from GOES-18 and GOES-19
2. **NOAA NDBC BuoyCAMs** — panoramic marine weather buoy cameras

No external dependencies. Uses only Python standard library (`urllib`, `json`, `datetime`, `html.parser`).

Reverse-engineered by direct inspection of:
- CDN directory listings at `cdn.star.nesdis.noaa.gov`
- GOES viewer pages at `star.nesdis.noaa.gov/GOES/`
- NDBC BuoyCAM JSON feed, KML feed (90+ stations catalogued), and station pages
- NDBC realtime and historical data file patterns

---

## Part 1 — GOES Satellite Imagery

### System overview

| Property | Value |
|---|---|
| CDN base | `https://cdn.star.nesdis.noaa.gov/` |
| Operational satellites | GOES-18 (West), GOES-19 (East) |
| Legacy satellite | GOES-16 (East) — CDN redirects all requests to GOES-19 |
| Update frequency | ~5 min (CONUS, Sector), ~10 min (Full Disk) |
| Image formats | JPEG (all sizes), GeoTIFF (CONUS/FD large resolutions) |
| Animation formats | GIF, MP4 |

### CDN URL anatomy

#### Latest image (always current, served from a fixed URL):
```
https://cdn.star.nesdis.noaa.gov/{SAT}/ABI/{VIEW}/{PRODUCT}/{RES}.jpg
https://cdn.star.nesdis.noaa.gov/{SAT}/ABI/{VIEW}/{PRODUCT}/latest.jpg
https://cdn.star.nesdis.noaa.gov/{SAT}/ABI/{VIEW}/{PRODUCT}/thumbnail.jpg
```

#### Timestamped image:
```
https://cdn.star.nesdis.noaa.gov/{SAT}/ABI/{VIEW}/{PRODUCT}/{TIMESTAMP}_{SAT}-ABI-{SECTOR}-{PRODUCT}-{RES}.jpg
```
- `TIMESTAMP` = `YYYYDDDHHSS` where `DDD` is the Julian day-of-year (001–366)

#### Rolling animation (always current):
```
https://cdn.star.nesdis.noaa.gov/{SAT}/ABI/{VIEW}/{PRODUCT}/{SAT}-{SECTOR}-{PRODUCT}-{RES}.gif
https://cdn.star.nesdis.noaa.gov/{SAT}/ABI/{VIEW}/{PRODUCT}/{SAT}-{SECTOR}-{PRODUCT}-{RES}.mp4
```

#### GLM (lightning) products use a parallel tree:
```
https://cdn.star.nesdis.noaa.gov/{SAT}/GLM/{VIEW}/{PRODUCT}/{RES}.jpg
```

#### Variables:
| Variable | Examples |
|---|---|
| `SAT` | `GOES19`, `GOES18`, `GOES16` |
| `VIEW` | `CONUS`, `FD`, `SECTOR/ne`, `SECTOR/se` |
| `PRODUCT` | `GEOCOLOR`, `FireTemperature`, `AirMass`, `08`, `EXTENT3` |
| `RES` | `416x250`, `625x375`, `1250x750`, `2500x1500`, `5000x3000`, `10000x6000` (CONUS) |

### Available satellites

| Satellite | Role | CDN Path |
|---|---|---|
| GOES-19 | East (operational) | `/GOES19/` |
| GOES-18 | West (operational) | `/GOES18/` |
| GOES-16 | East (legacy) | `/GOES16/` → redirects to GOES-19 |

### GOES-19 East sectors

| Code | Name |
|---|---|
| `cam` | Central America |
| `can` | Canada |
| `car` | Caribbean |
| `cgl` | Central Great Lakes |
| `eep` | Eastern Equatorial Pacific |
| `eus` | Eastern United States |
| `ga` | Gulf of Alaska |
| `mex` | Mexico |
| `na` | North Atlantic |
| `ne` | Northeast United States |
| `nr` | Northern Rockies |
| `nsa` | North South America |
| `pnw` | Pacific Northwest |
| `pr` | Puerto Rico |
| `psw` | Pacific Southwest |
| `se` | Southeast United States |
| `smv` | Southern Mississippi Valley |
| `sp` | Southern Plains |
| `sr` | Southern Rockies |
| `ssa` | South South America |
| `taw` | Tropical Atlantic – Wide |
| `umv` | Upper Mississippi Valley |

### GOES-18 West sectors

| Code | Name |
|---|---|
| `ak` | Alaska |
| `ar` | Arctic |
| `cak` | Central Alaska |
| `eep` | Eastern Equatorial Pacific |
| `gwas` | Great Western Atlantic / Sargasso |
| `hi` | Hawaii |
| `np` | North Pacific |
| `pnw` | Pacific Northwest |
| `psw` | Pacific Southwest |
| `sea` | Southeast Alaska |
| `tpw` | Tropical Pacific – Wide |
| `tsp` | Tropical South Pacific |
| `wus` | Western United States |

### ABI Products

#### RGB composites (available in CONUS, FD, SECTOR):

| Product key | Description |
|---|---|
| `GEOCOLOR` | GeoColor – True color day / IR night |
| `AirMass` | Air Mass RGB |
| `FireTemperature` | Fire Temperature RGB |
| `Dust` | Dust RGB |
| `Sandwich` | Sandwich RGB (Bands 3 & 13) |
| `DayNightCloudMicroCombo` | Day-Night Cloud Micro Combo RGB |
| `DayConvection` | Day Convection RGB (FD only) |
| `DMW` | Derived Motion Winds (CONUS/FD) |

#### Individual ABI spectral bands (01–16):

| Band | Description |
|---|---|
| `01` | Visible – blue (0.47 µm) |
| `02` | Visible – red (0.64 µm) |
| `03` | Near-IR – Veggie (0.86 µm) |
| `07` | IR – shortwave (3.9 µm) |
| `08` | IR – water vapor upper (6.2 µm) |
| `09` | IR – water vapor mid (6.9 µm) |
| `13` | IR – clean longwave (10.3 µm) |
| `16` | IR – CO₂ longwave (13.3 µm) |
*(all 16 bands available)*

#### GLM Lightning (separate instrument path `/GLM/`):
| Product key | Description |
|---|---|
| `EXTENT3` | GLM Flash Extent Density |

GLM products share the CONUS resolution set but top out at 5000×3000 (no 10000×6000 zip).

### Resolution reference

| View | Resolutions available |
|---|---|
| SECTOR | 300×300, 600×600, 1200×1200, 2400×2400 |
| CONUS | 416×250, 625×375, 1250×750, 2500×1500, 5000×3000, 10000×6000 |
| FD (Full Disk) | 339×339, 678×678, 1808×1808, 5424×5424, 10848×10848 |
| GLM CONUS | 416×250, 625×375, 1250×750, 2500×1500, 5000×3000 |

CONUS and FD also publish GeoTIFFs at the largest resolution (plus SHA-256 checksums).
High-resolution CONUS and FD JPEGs are also distributed as `.jpg.zip` compressed archives.

### Update cadence (confirmed by CDN directory timestamps)

| View | Interval |
|---|---|
| CONUS / Sector | Every ~5 minutes |
| Full Disk (FD) | Every ~10 minutes |
| GLM CONUS | Every ~5 minutes |

### File size reference (approximate)

| Resolution | CONUS GEOCOLOR |
|---|---|
| 416×250 | ~100 KB |
| 625×375 | ~220 KB |
| 1250×750 | ~700 KB |
| 2500×1500 | ~2 MB |
| 5000×3000 | ~6–7 MB |
| 10000×6000 | ~22–25 MB |

---

## Part 2 — NDBC BuoyCAMs

### System overview

| Property | Value |
|---|---|
| Operator | NOAA National Data Buoy Center (NDBC) |
| Total stations | ~77 (varies; ~69 active at any time) |
| Image format | JPEG, ~2880×300 panoramic strips (fisheye) |
| Update frequency | Approximately hourly during daylight hours |
| Coverage | Atlantic, Gulf of Mexico, Pacific, Alaska, Hawaii, Caribbean |

### Endpoints discovered

#### Live JSON station feed
```
GET https://www.ndbc.noaa.gov/buoycams.php
```
Returns a JSON array. Each element:
```json
{
  "id": "41002",
  "name": "SOUTH HATTERAS - 225 NM South of Cape Hatteras",
  "lat": 31.743,
  "lng": -74.955,
  "img": "Z24A_2026_03_27_1510.jpg",
  "width": 2880,
  "height": 300
}
```
`img` is `null` when no image is available (offline or nighttime).

#### Current image redirect
```
GET https://www.ndbc.noaa.gov/buoycam.php?station={STATION_ID}
→ 302 → https://www.ndbc.noaa.gov/images/buoycam/{FILENAME}
```
Returns HTTP 200 JPEG if current, or an error message if stale (>16 hours).

#### Direct image URL pattern
```
https://www.ndbc.noaa.gov/images/buoycam/{CAM_CODE}_{YYYY}_{MM}_{DD}_{HHMM}.jpg
```
Example: `https://www.ndbc.noaa.gov/images/buoycam/Z24A_2026_03_27_1510.jpg`

The `CAM_CODE` (e.g. `Z24A`) is an internal camera identifier, not the station ID.

#### KML feed (refreshed every 30 minutes)
```
https://www.ndbc.noaa.gov/kml/buoycams.kml        (wrapper with NetworkLink)
https://www.ndbc.noaa.gov/kml/buoycams_as_kml.php  (actual KML data)
```

#### Station weather data
```
Latest obs (text):   https://www.ndbc.noaa.gov/data/latest_obs/{STATION_ID}.txt
Latest obs (RSS):    https://www.ndbc.noaa.gov/data/latest_obs/{STATION_ID}.rss
Realtime 45-day:     https://www.ndbc.noaa.gov/data/realtime2/{STATION_ID}.txt
Spectral wave 45-day:https://www.ndbc.noaa.gov/data/realtime2/{STATION_ID}.spec
Historical annual:   https://www.ndbc.noaa.gov/data/historical/{type}/{station_id}{code}{YEAR}.txt.gz
Monthly (curr year): https://www.ndbc.noaa.gov/data/stdmet/{Mon}/{STATION_ID}.txt.gz
Station page:        https://www.ndbc.noaa.gov/station_page.php?station={STATION_ID}
```

The realtime2 standard met columns: `YY MM DD hh mm WDIR WSPD GST WVHT DPD APD MWD PRES ATMP WTMP DEWP VIS PTDY TIDE`

The .spec (spectral wave) columns: `YY MM DD hh mm WVHT SwH SwP WWH WWP SwD WWD STEEPNESS APD MWD`

#### Historical data type codes

| `data_type` | Filename code | Contents |
|---|---|---|
| `stdmet` | `h` | Standard meteorological (wind, wave, pressure, temp) |
| `cwind` | `c` | Continuous 10-min wind samples |
| `swden` | `w` | Spectral wave energy density |
| `swdir` | `d` | Spectral wave direction (first descriptor) |
| `swdir2` | `i` | Spectral wave direction (second descriptor) |
| `swr1` | `j` | Spectral r1 coefficient |
| `swr2` | `k` | Spectral r2 coefficient |
| `adcp` | `a` | Acoustic Doppler current profiler |
| `supl` | `s` | Supplemental (conductivity/salinity) |

Example: `https://www.ndbc.noaa.gov/data/historical/stdmet/41002h2024.txt.gz`

#### All-station latest obs bulk file
```
https://www.ndbc.noaa.gov/data/latest_obs/latest_obs.txt
```
Single flat file with current observations for every active NDBC station.
Columns: `STN LAT LON YYYY MM DD hh mm WDIR WSPD GST WVHT DPD APD MWD PRES PTDY ATMP WTMP DEWP VIS TIDE`

#### KML / GIS feeds
```
https://www.ndbc.noaa.gov/kml/marineobs_by_pgm.kml     (all obs by program)
https://www.ndbc.noaa.gov/kml/marineobs_by_owner.kml   (all obs by owner)
https://www.ndbc.noaa.gov/kml/buoycams.kml             (BuoyCAM stations wrapper)
https://www.ndbc.noaa.gov/kml/buoycams_as_kml.php      (BuoyCAM KML, refreshed 30 min)
```

#### NetCDF / THREDDS access
```
https://dods.ndbc.noaa.gov/                            (THREDDS catalog root)
https://dods.ndbc.noaa.gov/oceansites/                 (OceanSITES data)
```

---

## Python Client Usage

### GOES Satellite

```python
from noaa_cams_client import GOESClient, GOES19_SECTORS, ABI_COMPOSITES, ABI_BANDS

# Create a client for GOES-19 (East)
g = GOESClient("GOES19")

# Latest CONUS GeoColor image URLs at all resolutions
urls = g.conus_urls("GEOCOLOR")
# {'416x250': 'https://cdn.star...', '625x375': '...', ...}

# Latest Northeast sector
urls = g.sector_urls("ne", "GEOCOLOR")

# Full Disk
urls = g.fulldisk_urls("GEOCOLOR")

# Single URL (latest, no resolution specified → largest)
url = g.latest_image_url("GEOCOLOR", "CONUS")
url = g.latest_image_url("GEOCOLOR", "SECTOR", sector="se")
url = g.latest_image_url("GEOCOLOR", "FD")

# Specific resolution
url = g.latest_image_url("GEOCOLOR", "CONUS", resolution="1250x750")

# ABI spectral band
url = g.latest_image_url("13", "SECTOR", resolution="1200x1200", sector="ne")

# GLM lightning
url = g.latest_image_url("EXTENT3", "SECTOR", resolution="2400x2400",
                          sector="ne", instrument="GLM")

# Thumbnail
url = g.thumbnail_url("GEOCOLOR", "CONUS")

# Rolling animations
gif_url = g.latest_animation_url("GEOCOLOR", "CONUS", "625x375", fmt="gif")
mp4_url = g.latest_animation_url("GEOCOLOR", "CONUS", "625x375", fmt="mp4")

# GOES-18 West
g18 = GOESClient("GOES18")
url = g18.latest_image_url("GEOCOLOR", "CONUS")
url = g18.sector_urls("pnw", "FireTemperature")["1200x1200"]

# Timestamped image at a specific UTC time
from datetime import datetime, timezone
dt = datetime(2026, 3, 27, 16, 21, tzinfo=timezone.utc)
url = g.timestamped_image_url(dt, "GEOCOLOR", "CONUS", "2500x1500")
# → https://cdn.star.nesdis.noaa.gov/GOES19/ABI/CONUS/GEOCOLOR/20260861621_GOES19-ABI-CONUS-GEOCOLOR-2500x1500.jpg

# List all available historical images in a directory
images = g.list_available_images("GEOCOLOR", "CONUS")
latest = images[-1]
print(latest["url"], latest["dt"])

# Download latest image
path = g.download_latest("/tmp/goes", "GEOCOLOR", "CONUS", resolution="2500x1500")

# Download image at a specific time
path = g.download_image_at(dt, "/tmp/goes", "GEOCOLOR", "CONUS", "2500x1500")

# Get current scan mode
mode = g.get_mode()  # e.g. "3" (Mode 3 = flex scanning)
```

### NDBC BuoyCAMs

```python
from noaa_cams_client import BuoyCAMClient, download_image

bc = BuoyCAMClient()

# All stations (77 total)
stations = bc.get_stations()

# Only active stations (have a current image)
active = bc.active_stations()
print(f"{len(active)} active stations")

# Single station metadata
stn = bc.get_station("41002")
print(stn["name"], stn["lat"], stn["lng"])

# Current image URLs
redirect_url = bc.current_image_url("41002")
# https://www.ndbc.noaa.gov/buoycam.php?station=41002  (302 → JPEG)

direct_url = bc.current_image_direct_url("41002")
# https://www.ndbc.noaa.gov/images/buoycam/Z24A_2026_03_27_1510.jpg

# Parse filename metadata
meta = bc.parse_image_metadata("Z24A_2026_03_27_1510.jpg")
# {'cam_code': 'Z24A', 'year': '2026', 'month': '03', 'day': '27',
#  'time_utc': '1510', 'dt': datetime(2026, 3, 27, 15, 10, tzinfo=utc),
#  'url': 'https://...'}

# Full summary with all URLs
summary = bc.station_summary("41002")

# Weather data
txt = bc.get_latest_weather("41002")       # human-readable text
rss = bc.get_latest_weather_rss("41002")   # RSS/XML
tsv = bc.get_realtime_data("41002")        # 45-day tab-separated table
records = bc.parse_realtime_data(tsv)      # list of dicts

# Historical data URL (gzip-compressed, download manually)
hist_url = bc.historical_data_url("41002", 2024)
# → https://www.ndbc.noaa.gov/data/historical/stdmet/41002h2024.txt.gz

# Historical spectral wave energy data
spec_hist_url = bc.historical_data_url("41002", 2024, data_type="swden")
# → https://www.ndbc.noaa.gov/data/historical/swden/41002w2024.txt.gz

# Spectral wave 45-day rolling file
spec_url = bc.spectral_wave_url("41002")
# → https://www.ndbc.noaa.gov/data/realtime2/41002.spec

# Monthly data (current year only)
monthly_url = bc.monthly_data_url("41002", 2026, 1)
# → https://www.ndbc.noaa.gov/data/stdmet/Jan/41002.txt.gz

# KML feed
kml = bc.get_kml()  # XML string

# Download current image for one station
path = bc.download_current_image("41002", "/tmp/buoycam")

# Download all active station images (generator)
for station_id, local_path in bc.download_all_current_images("/tmp/buoycam"):
    print(station_id, local_path)

# Limit number of downloads
for station_id, local_path in bc.download_all_current_images("/tmp/buoycam", max_stations=5):
    print(station_id, local_path)
```

### One-liner helpers

```python
from noaa_cams_client import goes_latest_url, buoycam_current_url, buoycam_stations

url = goes_latest_url("GOES19", "GEOCOLOR", "CONUS", "2500x1500")
url = buoycam_current_url("41002")
stations = buoycam_stations()
```

### Generic download

```python
from noaa_cams_client import download_image

path = download_image(url, "/tmp/myimage.jpg")
```

---

## Timestamp format (GOES)

GOES CDN timestamps use the format `YYYYDDDHHSS` where:
- `YYYY` = 4-digit year
- `DDD` = Julian day-of-year (001–366)
- `HH` = UTC hour (00–23)
- `SS` = UTC minute (00–59)

Example: `20260861621` = year 2026, day 86 (March 27), 16:21 UTC

Conversion utilities:
```python
from noaa_cams_client import GOESClient
from datetime import datetime, timezone

ts = GOESClient._datetime_to_goes_timestamp(datetime(2026, 3, 27, 16, 21, tzinfo=timezone.utc))
# '20260861621'

dt = GOESClient.goes_timestamp_to_datetime('20260861621')
# datetime(2026, 3, 27, 16, 21, tzinfo=utc)
```

---

## Notes and limitations

### BuoyCAMs
- The `buoycams.php` JSON feed is the authoritative source for active stations.
- `img` is `null` for stations that are offline or not yet illuminated (nighttime).
- Images are panoramic fisheye strips (~2880×300 pixels), not standard aspect-ratio photos.
- The internal camera code (e.g. `Z24A`) embedded in the filename is NOT the NDBC station ID.
- An image older than 16 hours is flagged as stale; `buoycam.php` returns an error text rather than a redirect in that case.
- There is no public API for historical BuoyCAM images; only current images are accessible. Historical meteorological data (non-image) is available back to station commissioning via `stdmet/`.
- The `KNOWN_BUOYCAM_STATIONS` dict in the module provides a static list of ~35 representative stations (Atlantic, Pacific, Hawaii, Caribbean) discovered from the KML feed as of 2026-03-27. The live JSON feed returns ~77–90 stations.
- Several stations were noted as having no image in the KML: 42003, 42020, 44025, 46053, 46054, 46076, 46078 (typically camera offline or maintenance).

### GOES
- GOES-16 is a legacy satellite; its CDN URLs return HTTP 302 redirects to GOES-19 equivalents.
- The `latest.jpg` and `thumbnail.jpg` files are updated every scan cycle (~5 min for CONUS/Sector).
- Rolling animation GIFs/MP4s are regenerated periodically (not every scan); cache headers reflect this.
- GeoTIFF files (`.tif`) are available for CONUS 5000×3000 and FD 10848×10848; each has a SHA-256 checksum file alongside.
- Mesoscale (MESO) sectors are transient: they activate during weather events and are identified by lat/lon coordinates (e.g. `38N-99W`) rather than named codes.
- The `mode.txt` file in each satellite's ABI directory reports the current scan mode ("3" = Mode 3 flex, "6" = Mode 6 continuous full-disk).
- The GOES viewer pages (`star.nesdis.noaa.gov/GOES/`) confirmed satellite designations: G19 = GOES-East, G18 = GOES-West; viewer PHP parameters use `sat=G19` while CDN paths use `GOES19`.

---

## File structure

```
noaa_cams_client.py
│
├── GOESClient                     GOES satellite imagery
│   ├── latest_image_url()
│   ├── thumbnail_url()
│   ├── latest_animation_url()
│   ├── timestamped_image_url()
│   ├── list_available_images()
│   ├── get_latest_metadata()
│   ├── download_latest()
│   ├── download_image_at()
│   ├── get_mode()
│   ├── sector_urls()
│   ├── conus_urls()
│   ├── fulldisk_urls()
│   └── _datetime_to_goes_timestamp() / goes_timestamp_to_datetime()
│
├── BuoyCAMClient                  NDBC BuoyCAM imagery
│   ├── get_stations()
│   ├── get_station()
│   ├── active_stations()
│   ├── current_image_url()
│   ├── current_image_direct_url()
│   ├── image_url_from_filename()
│   ├── parse_image_metadata()
│   ├── weather_data_url()
│   ├── realtime_data_url()
│   ├── spectral_wave_url()           (45-day .spec file)
│   ├── historical_data_url()         (annual archives, all data types)
│   ├── monthly_data_url()            (current-year monthly files)
│   ├── get_latest_weather()
│   ├── get_latest_weather_rss()
│   ├── get_realtime_data()
│   ├── parse_realtime_data()
│   ├── get_kml()
│   ├── download_current_image()
│   ├── download_all_current_images()
│   └── station_summary()
│
├── download_image()               Generic image download helper
├── goes_latest_url()              One-liner
├── buoycam_current_url()          One-liner
├── buoycam_stations()             One-liner
│
├── GOES_SATELLITES                Dict of satellite IDs and descriptions
├── GOES19_SECTORS                 Dict of GOES-East sector codes → names
├── GOES18_SECTORS                 Dict of GOES-West sector codes → names
├── ABI_COMPOSITES                 Dict of composite product keys → descriptions
├── ABI_BANDS                      Dict of band numbers "01"–"16" → descriptions
├── GLM_PRODUCTS                   Dict of GLM product keys
├── SECTOR_RESOLUTIONS             List of sector resolution strings
├── CONUS_RESOLUTIONS              List of CONUS resolution strings
├── FD_RESOLUTIONS                 List of Full Disk resolution strings
├── GLM_CONUS_RESOLUTIONS          List of GLM CONUS resolution strings
└── KNOWN_BUOYCAM_STATIONS         Static dict of ~35 BuoyCAM stations from KML
```
