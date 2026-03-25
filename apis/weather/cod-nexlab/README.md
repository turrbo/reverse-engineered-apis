# COD NEXLAB Python Client

Reverse-engineered Python client for **College of DuPage NEXLAB**
(`https://weather.cod.edu`) — a free, public weather data portal operated by
the College of DuPage Meteorology department.

No API key or login is required. All endpoints were discovered through static
HTML/JavaScript analysis of the COD NEXLAB website.

---

## What is COD NEXLAB?

COD NEXLAB is one of the most comprehensive free meteorological data portals
on the internet. It provides:

- Full-resolution **NEXRAD dual-pol radar** imagery for every CONUS, Alaska,
  Hawaii, and US territory radar site
- **GOES-East/-West ABI satellite** imagery — all 16 bands and 6 RGB composites
- **Numerical weather prediction models**: GFS, NAM, HRRR, RAP, ECMWF,
  NAMNST, RDPS, GDPS, GEFS, CFS, SREF
- **Surface analysis** maps (synoptic fronts, moisture convergence, etc.)
- **NWS text products** (raw text and structured JSON)
- **Local Storm Reports** (JSON API)
- **Severe weather warnings** (JSON API)
- **Forecast soundings** (model skew-T log-P diagrams)
- **Campus weather / Storm Ready** status for College of DuPage

---

## Discovered API Endpoints

### NEXRAD Radar

#### File Listing API
```
GET https://weather.cod.edu/satrad/nexrad/assets/php/get-files.php
    ?parms={SITE}-{PRODUCT}-{LOOP}-{N_IMAGES}-{RATE}
```

| Parameter  | Description                                          |
|------------|------------------------------------------------------|
| `SITE`     | 3-letter NEXRAD site ID (e.g. `LOT`, `OKX`, `FFC`)  |
| `PRODUCT`  | Level-3 product code (see table below)               |
| `LOOP`     | `1` to autoplay, `0` for static                      |
| `N_IMAGES` | Number of images to return (3–200)                   |
| `RATE`     | Animation rate in ms (50, 100, 250, 500, 1000)       |

**Response** (JSON):
```json
{
  "img": [900, 900],
  "lores": [true, false],
  "err": false,
  "files": [
    "https://weather.cod.edu/wxdata/nexrad/LOT/N0B/LOT.N0B.20260325.0211.gif",
    "..."
  ]
}
```

**Image URL pattern:**
```
https://weather.cod.edu/wxdata/nexrad/{SITE}/{PRODUCT}/{SITE}.{PRODUCT}.{YYYYMMDD}.{HHMM}.gif
```

#### Server-rendered Animated GIF
```
GET https://weather.cod.edu/satrad/nexrad/assets/php/scripts/mkgif.php
    ?parms={SITE}-{PRODUCT}-{N_FRAMES}-{RATE}
```

#### ZIP Archive of Frames
```
GET https://weather.cod.edu/satrad/nexrad/assets/php/scripts/mkzip.php
    ?parms={SITE}-{PRODUCT}-{N_FRAMES}
```

#### NEXRAD Product Codes

| Code  | Product                             | Tilts |
|-------|-------------------------------------|-------|
| N0B   | Base Reflectivity                   | 1     |
| N1B   | Base Reflectivity                   | 2     |
| N2B   | Base Reflectivity                   | 3     |
| N3B   | Base Reflectivity                   | 4     |
| N0G   | Base Velocity                       | 1     |
| N1G   | Base Velocity                       | 2     |
| N2U   | Base Velocity                       | 3     |
| N3U   | Base Velocity                       | 4     |
| N0S   | Storm Relative Mean Velocity        | 1     |
| N0X   | Differential Reflectivity (ZDR)     | 1–4   |
| N0C   | Correlation Coefficient (CC)        | 1–4   |
| N0K   | Specific Differential Phase (KDP)   | 1–4   |
| OHA   | One-Hour Precipitation              | —     |
| DSP   | Storm Total Precipitation           | —     |
| DVL   | Vertically Integrated Liquid (VIL)  | —     |
| EET   | Echo Tops                           | —     |
| NVW   | Vertical Wind Profile               | —     |
| HHC   | Hybrid Hydrometeor Classification   | —     |
| N0Q   | Base Refl. (legacy alias, → N0B)    | 1     |
| N0U   | Base Vel. (legacy alias, → N0G)     | 1     |

---

### GOES Satellite Imagery

The satellite page inlines image URLs directly in the HTML. Fetch the page
with custom `parms` to get the image list.

#### Satellite Page (HTML with embedded image URLs)
```
GET https://weather.cod.edu/satrad/
    ?parms={SCALE}-{SECTOR}-{BAND}-{N_IMAGES}-{LOOP}-{RATE}-{NTH}
    &checked={OVERLAYS}
    &colorbar={COLORBAR}
```

| Parameter  | Description                                              |
|------------|----------------------------------------------------------|
| `SCALE`    | `continental`, `regional`, `subregional`, `local`, `global`, `meso` |
| `SECTOR`   | Sector name (see Sectors table below)                    |
| `BAND`     | Band/product code (`02`, `13`, `comp_radar`, etc.)       |
| `N_IMAGES` | Number of frames to embed (3–200)                        |
| `LOOP`     | `1` to autoplay on page load                             |
| `RATE`     | Animation rate in ms                                     |
| `NTH`      | Take every Nth frame (1 = every frame, 2 = every other)  |
| `OVERLAYS` | Comma-separated overlay names (e.g. `map,counties,ww`)   |
| `COLORBAR` | Colorbar name (`data`, `sst`, `tpw`, etc.)               |

#### Current Image (always-fresh)
```
https://weather.cod.edu/wxdata/satellite/{SCALE}/{SECTOR}/current/{SECTOR}.{BAND}.jpg
```

#### Archived Image (direct URL)
```
https://weather.cod.edu/wxdata/satellite/{SCALE}/{SECTOR}/{BAND}/{SECTOR}.{BAND}.{YYYYMMDD}.{HHmmss}.jpg
```

#### Map Layer (static geographic overlay)
```
https://weather.cod.edu/wxdata/satellite/{SCALE}/{SECTOR}/maps/{SECTOR}_{LAYER}.png
```
Layers: `map`, `counties`, `cwa`, `latlon`, `rivers`, `usstrd`, `ushw`, `usint`, `artcc`

#### Dynamic Overlay (GOES-derived product)
```
https://weather.cod.edu/wxdata/satellite/{SCALE}/{SECTOR}/overlays/{OVERLAY}/{SECTOR}-{OVERLAY}.{YYYYMMDDHHmmss}.png
```
Overlays: `acha`, `acht`, `actp`, `dsi_cape`, `sst`, `lst`, `tpw`, `rrqpe`, `adp_dust`, `adp_smoke`

#### Colorbar Image
```
https://weather.cod.edu/wxdata/satellite/colorbars/{COLORBAR}.png
```

#### ABI Band Codes

| Code  | Description                      |
|-------|----------------------------------|
| 01    | Visible — Blue (0.47 µm)        |
| 02    | Visible — Red (0.64 µm)         |
| 03    | Near-IR — Green/Veggie (0.86 µm)|
| 04    | Near-IR — Cirrus (1.37 µm)      |
| 05    | Near-IR — Snow/Ice (1.6 µm)     |
| 06    | Near-IR — Cloud Particle Size    |
| 07    | Short-Wave IR (3.9 µm)          |
| 08    | Upper-level Water Vapor (6.2 µm) |
| 09    | Mid-level Water Vapor (6.9 µm)   |
| 10    | Lower-level Water Vapor (7.3 µm) |
| 11    | Cloud Top Phase (8.4 µm)         |
| 12    | Ozone (9.6 µm)                   |
| 13    | Clean Long-wave IR (10.3 µm)     |
| 14    | Long-wave IR (11.2 µm)           |
| 15    | Dirty Long-wave IR (12.3 µm)     |
| 16    | CO2 Long-wave IR (13.3 µm)       |
| comp_radar | Mosaic NEXRAD Radar             |
| ss_radar   | NEXRAD Dual-Pol Sites           |
| truecolor  | True-Color RGB composite        |
| airmass    | Colorized Airmass RGB           |
| ntmicro    | Nighttime Microphysics RGB      |
| dcphase    | Day Cloud Phase RGB             |
| simplewv   | Simple Water Vapor RGB          |
| sandwich   | Visible+IR Sandwich             |

#### Satellite Sectors

**Continental:** `conus`

**Regional (US):** `us`, `ne`, `ma`, `se`, `ngp`, `gl`, `nil`, `mw`, `cgp`,
`sgp`, `sw`, `nw`, `gbsn`, `can`, `wcan`, `ecan`, `ak`, `hi`, `prregional`

**Subregional:** All 50 US state abbreviations (e.g. `IL`, `TX`, `CA`)

**Local:** `N_Illinois`, `Chicago`, `Iowa`, `S_Minnesota`, `Ohio`, `Indiana`,
`Kansas`, `Oklahoma`, `Missouri`, `Houston`, `Dallas`, `Denver`, `Salt_Lake`,
`Portland`, `Seattle`, and many more

**Meso:** `meso1`, `meso2`, `meso3`, `meso4` (GOES mesoscale sectors)

**Global:** `fulldiskeast`, `fulldiskwest`, `northernhemi`, `southernhemi`,
`northamerica`, `equatorial`, `atlantic`, etc.

---

### Forecast Models

#### File Listing API
```
GET https://weather.cod.edu/forecast/assets/php/scripts/get-files.php
    ?parms={RUN}-{MODEL}-{SECTOR}-{CATEGORY}-{PRODUCT}-{FHOUR}-{LOOP}-{RATE}
```

| Parameter  | Description                                                 |
|------------|-------------------------------------------------------------|
| `RUN`      | Model run: `YYYYMMDDhh` (e.g. `2026032418`)                |
| `MODEL`    | Model name (see table below)                                |
| `SECTOR`   | Geographic sector (e.g. `US`, `MW`, `NE`)                   |
| `CATEGORY` | Product category (`sfc`, `prec`, `500`, `850`, etc.)        |
| `PRODUCT`  | Product within category (`temp`, `radar`, `rhum`, etc.)      |
| `FHOUR`    | Starting forecast hour (e.g. `0`, `24`, `48`)               |
| `LOOP`     | `1` to autoplay, `0` for static                             |
| `RATE`     | Animation rate in ms                                        |

**Response** (JSON):
```json
{
  "parms": ["2026032418", "GFS", "US", "prec", "radar", "0", "0", "100"],
  "img": {"0": 800, "1": 600, "mime": "image/png"},
  "err": "false",
  "files": [
    "https://weather.cod.edu/wxdata/forecast/GFS/2026032418/US/GFSUS_prec_radar_000.png",
    "https://weather.cod.edu/wxdata/forecast/GFS/2026032418/US/GFSUS_prec_radar_003.png",
    "..."
  ],
  "readouts": [
    "https://weather.cod.edu/wxdata/forecast/GFS/2026032418/US/readout/GFSUS_prec_radar_000.txt.gz",
    "..."
  ]
}
```

**Image URL pattern:**
```
https://weather.cod.edu/wxdata/forecast/{MODEL}/{RUN}/{SECTOR}/
  {MODEL}{SECTOR}_{CATEGORY}_{PRODUCT}_{FHH}.png
```

**Readout URL pattern (gzipped grid data):**
```
https://weather.cod.edu/wxdata/forecast/{MODEL}/{RUN}/{SECTOR}/readout/
  {MODEL}{SECTOR}_{CATEGORY}_{PRODUCT}_{FHH}.txt.gz
```

#### Best Run API
```
GET https://weather.cod.edu/forecast/assets/php/scripts/get-best.php
    ?parms={MODEL}-{VALID_TIME}-{START_HOUR}
```

Returns the best available model run for a requested valid time.

```json
{
  "result": "2026032418+6",
  "validIn": "2026032500",
  "validOut": "2026032500",
  "validMatches": ["2026032418+6", "2026032412+12", "..."],
  "code": "10",
  "formatted": {
    "runIn": "00Z from 3/25/2026",
    "runOut": "18Z from 3/24/2026",
    "runChange": -6
  }
}
```

#### Menu API (product navigation HTML)
```
GET https://weather.cod.edu/forecast/assets/php/scripts/get-menu.php
    ?parms={RUN}-{MODEL}-{SECTOR}-{CATEGORY}-{PRODUCT}-{FHOUR}-{LOOP}-{RATE}
```

Returns the HTML fragment with product buttons and hour selector table.

#### Map API (sector map HTML)
```
GET https://weather.cod.edu/forecast/assets/php/scripts/get-map.php
    ?model={MODEL}
```

Returns an HTML fragment with the geographic sector selection map.
The `data-sectors` attribute lists all valid sector codes for that model.

#### Available Models

| Model  | Full Name                          | Run Step | Runs/Day |
|--------|------------------------------------|----------|----------|
| HRRR   | High Resolution Rapid Refresh      | 1h       | 24       |
| RAP    | Rapid Refresh                      | 3h       | 8        |
| NAM    | North American Mesoscale           | 6h       | 4        |
| NAMNST | NAM CONUS Nest 3km                 | 6h       | 4        |
| RDPS   | GEM Regional Det. (Canada)         | 6h       | 4        |
| SREF   | Short Range Ensemble               | 6h       | 4        |
| GDPS   | GEM Global Det. (Canada)           | 12h      | 2        |
| ECMWF  | European Centre MWRF               | 6h       | 4        |
| GFS    | Global Forecast System             | 6h       | 4        |
| GEFS   | Global Ensemble Forecast           | 6h       | 4        |
| CFS    | Climate Forecast System            | 6h       | 4        |

#### Model Product Categories

| Category | Products include…                                              |
|----------|----------------------------------------------------------------|
| `sfc`    | temp, dewp, rhum, thetae, mslpsa, avort, wetblb, vis          |
| `prec`   | radar, prec, precacc, precacc6/12/24, cprec, pwat, cloud      |
| `con`    | mlcape, mucape, sbcape, 3kmhel, 3kmehi, shear, scp, lsi       |
| `850`    | temp, dewp, rhum, thetae, tadv, vvel, spd, hgtsa              |
| `700`    | temp, rhum, vvel, avort, spd                                  |
| `500`    | temp, hgtsa, avort, rhum, vvel, spd, spdsa, uwndsa            |
| `250`    | spd, spdsa, hgtsa, rhum, uwndsa                               |
| `winter` | ptype, kuchsnow, kuchsnow6/12/24, kratio, snow, frzra, cthk  |

---

### Forecast Soundings

```
GET https://weather.cod.edu/forecast/fsound/index.php
    ?type={RUN}|{MODEL}|{SECTOR}|{CATEGORY}|{PRODUCT}|{FHOUR}|{LAT},{LON}|{PARCEL}|{WXTYPE}
```

| Parameter | Description                                              |
|-----------|----------------------------------------------------------|
| `RUN`     | Model run `YYYYMMDDhh`                                  |
| `MODEL`   | Model name                                               |
| `SECTOR`  | Sector code                                              |
| `FHOUR`   | Forecast hour                                            |
| `LAT,LON` | Decimal degrees (e.g. `41.85,-87.65`)                   |
| `PARCEL`  | `sb` (surface-based), `ml` (mixed-layer), `mu` (most-unstable) |
| `WXTYPE`  | `wxdata` (standard), `severe`, or `winter`              |

The page displays a SHARPpy skew-T log-P diagram with full sounding indices.

---

### Surface Analysis

**Synoptic fronts GIF:**
```
https://weather.cod.edu/wxdata/surface/{REGION}/contour/{REGION}.{PRODUCT}.{YYYYMMDD}.{HH}.gif
```

**High-resolution fronts GIF (current):**
```
https://weather.cod.edu/wxdata/surface/US_zoom/contour/current/USZOOM.fronts.gif
```

**Surface PDF maps:**
```
https://weather.cod.edu/wxdata/surface/{REGION}/pdf/{REGION}.{YYYYMMDD}.{HH}.pdf
```

**Regions:** `US`, `ne`, `se`, `mw`, `cgp`, `sgp`, `sw`, `nw`, `can`, `wcan`, `ecan`

**Products:** `fronts`, `mdiv`, `pfalls`, `thte`, `tpsl`

**Mesoscale analysis page:**
```
https://weather.cod.edu/climate-decom/flanis/analysis/surface/index.php?type={REGION}-{PRODUCT}-1
```

---

### NWS Text Products

#### Raw Text Products
```
GET https://weather.cod.edu/textserv/raw/{OFFICE}/{PRODUCT_ID}/
```

Example: `https://weather.cod.edu/textserv/raw/KLOT/NOUS63_FTMLOT/`

#### Active Severe Warnings (JSON)
```
GET https://weather.cod.edu/textserv/json/svr/active
GET https://weather.cod.edu/textserv/json/svr/active-2   (extended fields)
```

Response: JSON array of warning objects.

#### Recent (non-active) Severe Warnings (JSON)
```
GET https://weather.cod.edu/textserv/json/svr/nonactive-2
```

#### Local Storm Reports (JSON, gzip-encoded)
```
GET https://weather.cod.edu/textserv/json/lsr?days={N}
```

Returns a JSON array (gzip-compressed). Each LSR object:
```json
{
  "county": "Ponce",
  "event": "Landslide",
  "latlon": [18.13, -66.58],
  "location": "Anon",
  "office": "JSJ",
  "office_plain": "San Juan PR",
  "remark": "A landslide was reported ...",
  "source": "Emergency Mngr",
  "state": "PR",
  "valid_time": "23:00 UTC Tuesday, March 24",
  "valid_time_ts": "1774393200"
}
```

**Important:** Must use `Accept-Encoding: gzip` or decode manually.

#### Warnings Dashboard (HTML)
```
GET https://weather.cod.edu/textserv/warnings
```

#### Local Storm Reports Dashboard (HTML)
```
GET https://weather.cod.edu/textserv/lsr
```

---

### Campus Weather

#### Storm Ready Status
```
GET https://weather.cod.edu/campusweather/assets/php/scripts/SRstatus.php
```

Returns a plain-text color code: `none`, `blue`, `green`, `yellow`, or `red`.

| Color  | Meaning                                      |
|--------|----------------------------------------------|
| none   | No severe weather threat                     |
| blue   | CONDITION BLUE – general severe weather watch |
| green  | CONDITION GREEN – organized storm approaching |
| yellow | CONDITION YELLOW – imminent severe weather    |
| red    | CONDITION RED – tornado or extreme danger     |

---

### Site Alert Messages

```
GET https://weather.cod.edu/assets/javascript/alert/{SECTION}.js
```

Sections: `nexrad`, `forecast`, `satrad`

Returns a JavaScript snippet that the page uses to display alert banners.

---

### WFO–NEXRAD Site Mapping (JSON)

```
GET https://weather.cod.edu/satrad/nexrad/assets/json/wfo-rda.json
```

Maps NWS Weather Forecast Office (WFO) codes to associated NEXRAD radar
site IDs.

---

## wxdata Directory Structure

The `wxdata` file server at `https://weather.cod.edu/wxdata/` is browseable
(with some path restrictions). Key subdirectories:

```
/wxdata/
├── nexrad/
│   └── {SITE}/
│       └── {PRODUCT}/           # GIF images
│           └── {SITE}.{PROD}.{YYYYMMDD}.{HHMM}.gif
├── satellite/
│   └── {SCALE}/
│       └── {SECTOR}/
│           ├── current/          # Single most-recent image
│           │   └── {SECTOR}.{BAND}.jpg
│           ├── {BAND}/           # Archived images
│           │   └── {SECTOR}.{BAND}.{YYYYMMDD}.{HHmmss}.jpg
│           ├── maps/             # Static geographic layers
│           │   └── {SECTOR}_{LAYER}.png
│           ├── overlays/         # Dynamic product overlays
│           │   └── {PRODUCT}/{SECTOR}-{PRODUCT}.{TIMESTAMP}.png
│           └── colorbars/
│               └── {PRODUCT}.png
├── forecast/
│   └── {MODEL}/
│       └── {YYYYMMDDHH}/         # Run directory
│           └── {SECTOR}/
│               ├── {MODEL}{SECTOR}_{CAT}_{PROD}_{FHH}.png
│               └── readout/
│                   └── {MODEL}{SECTOR}_{CAT}_{PROD}_{FHH}.txt.gz
└── surface/
    └── {REGION}/
        ├── contour/
        │   └── {REGION}.{PRODUCT}.{YYYYMMDD}.{HH}.gif
        └── pdf/
            └── {REGION}.{YYYYMMDD}.{HH}.pdf
```

---

## Installation & Usage

No dependencies beyond the Python standard library are required.

```bash
python3 cod_nexlab_client.py   # runs the demo
```

Or use as a module:

```python
from cod_nexlab_client import CODNexlabClient

client = CODNexlabClient()

# Get radar images for Chicago (LOT)
result = client.get_nexrad_images("LOT", "N0B", num_images=24)
for url in result["files"]:
    print(url)

# Download the current CONUS IR satellite image
data = client.download_latest_satellite_image("continental", "conus", "13")
with open("conus_ir.jpg", "wb") as f:
    f.write(data)

# Get GFS model image list
result = client.get_model_images("GFS", "US", "prec", "radar")
print(result["files"][0])  # first (analysis) frame

# Local Storm Reports
lsrs = client.get_local_storm_reports(days=1)
print(f"{len(lsrs)} LSRs in the last 24 hours")

# Active severe warnings
warnings = client.get_severe_warnings_active()
print(f"{len(warnings)} active severe weather warnings")

# Campus storm-ready status
status = client.get_campus_storm_ready_status()
print(f"COD campus status: {status}")
```

---

## Notes & Rate Limiting

- COD NEXLAB is a free academic resource. All CORS headers are set to `*`.
- The server will rate-limit or block IPs that make excessive requests.
- Radar data is updated approximately every 5–7 minutes.
- GOES ABI data is updated every 5 minutes (CONUS), every 1 minute (meso).
- Model data is updated as each run completes (can be 2–4 hours after run time).
- Satellite data older than 3–4 days may be archived to Iowa State University.
- The `textserv/json/lsr` endpoint returns gzip-compressed JSON; use
  `Accept-Encoding: gzip` or decompress manually.

---

## Reverse Engineering Notes

### Discovery Method

All endpoints were discovered via static analysis (no browser automation):

1. Downloaded HTML pages from key sections (`/satrad/`, `/satrad/nexrad/`,
   `/forecast/`, `/text/`, `/analysis/`)
2. Extracted all linked JavaScript files (`behavior-desk.js`, `ani-desk.js`,
   `pageBehavior-desktop.php`, etc.)
3. Traced `$.get()` and `$.ajax()` calls to find PHP backend scripts
4. Tested PHP endpoints directly with `curl` to validate responses
5. Parsed embedded `window.modeljson` from `/forecast/` to enumerate all models
6. Scraped product menus via `get-menu.php` to enumerate all categories/products
7. Inspected `wxdata/` directory listings (Apache autoindex enabled on most paths)

### Key PHP Scripts

| Script | Description |
|--------|-------------|
| `/satrad/nexrad/assets/php/get-files.php` | NEXRAD image file listing |
| `/satrad/nexrad/assets/php/scripts/mkgif.php` | Server-side animated GIF render |
| `/satrad/nexrad/assets/php/scripts/mkzip.php` | ZIP archive of radar frames |
| `/forecast/assets/php/scripts/get-files.php` | Model image file listing |
| `/forecast/assets/php/scripts/get-best.php` | Best model run finder |
| `/forecast/assets/php/scripts/get-menu.php` | Product navigation menu HTML |
| `/forecast/assets/php/scripts/get-map.php` | Sector selection map HTML |
| `/campusweather/assets/php/scripts/SRstatus.php` | Campus Storm Ready status |

### Parameter Format

The COD site consistently uses a **hyphen-delimited string** as the primary
parameter key (`parms`). This single string encodes multiple positional
parameters:

- **Radar:** `{SITE}-{PRODUCT}-{LOOP}-{N_IMAGES}-{RATE}`
- **Satellite page:** `{SCALE}-{SECTOR}-{BAND}-{N_IMAGES}-{LOOP}-{RATE}-{NTH}`
- **Forecast model:** `{RUN}-{MODEL}-{SECTOR}-{CATEGORY}-{PRODUCT}-{FHOUR}-{LOOP}-{RATE}`

The server is generally lenient about extra parameters (it falls back to
sensible defaults if unrecognized values are passed).
