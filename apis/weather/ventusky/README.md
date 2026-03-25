# Ventusky API – Reverse-Engineered Documentation

> **Disclaimer**: These APIs are internal/undocumented and subject to change without notice.
> Use responsibly and respect the service's terms of use. Do not hammer endpoints.

---

## Overview

Ventusky (https://www.ventusky.com) is a weather visualization platform.
Its front-end is a single-page JavaScript application that fetches data from
several first-party and third-party backends.

### Reverse-Engineering Methodology

1. Fetched the main HTML page – extracted the `MapOptions` configuration object
   containing all model timeline metadata and API base URL hints from `<link rel="dns-prefetch">` tags.
2. Downloaded and analysed the minified JavaScript bundle
   (`https://static.ventusky.com/media/script-en.js`), which contains all URL
   templates as string literals.
3. Probed discovered endpoints with HTTP HEAD/GET requests to confirm format and
   verify response types.

---

## Base Domains

| Domain | Purpose |
|---|---|
| `data.ventusky.com` | Weather tile images (JPEG) and data JSON files |
| `static.ventusky.com` | Static assets, CSS, JS, base-map PNG tiles |
| `map.ventusky.com` | High-zoom OSM-style map tiles (zoom ≥ 13) |
| `api.ventusky.com` | REST API endpoints (hurricane tracks) |
| `webcams.ventusky.com` | Live webcam images and metadata |
| `www.ventusky.com` | Location search and reverse geocoding |
| `users.ventusky.com` | Authenticated user profile info |

---

## Endpoints

### 1. City Search

```
GET https://www.ventusky.com/ventusky_mesta.php?q={query}&lang={lang}
```

**Parameters**

| Name | Type | Description |
|---|---|---|
| `q` | string | City name query |
| `lang` | string | Language code (default `en`) |

**Response** – JSON array

```json
[
  {
    "lat": 51.5073359,
    "lon": -0.12765,
    "altitude": 25,
    "address": {
      "city": "London",
      "city_en": "London",
      "state": "England",
      "country": "United Kingdom",
      "tz_name": "Europe/London",
      "tz_offset": 0
    }
  }
]
```

---

### 2. Reverse Geocode / Nearest Named Locations

```
GET https://www.ventusky.com/ventusky_location.json.php?lat={lat}&lon={lon}&zoom={zoom}
```

**Parameters**

| Name | Type | Description |
|---|---|---|
| `lat` | float | Latitude |
| `lon` | float | Longitude |
| `zoom` | int | Map zoom level (affects result count) |

**Response** – JSON array

```json
[
  {
    "name": "New York",
    "ascii": "New York",
    "url": "new-york",
    "distance": 0,
    "id": 2930503,
    "lat": 40.7127281,
    "lon": -74.0060152
  }
]
```

The `url` field is the slug used in Ventusky city pages (e.g. `https://www.ventusky.com/new-york`).

---

### 3. Whole-World Weather Tile (JPEG Image)

```
GET https://data.ventusky.com/{yyyy}/{MM}/{dd}/{model}/whole_world/hour_{HH}{minutesFolder}/{model}_{layer}_{yyyyMMdd_HH}{minutes}.jpg
```

This is the main weather data visual layer served as an equirectangular JPEG.

**URL template variables**

| Variable | Description |
|---|---|
| `{yyyy}/{MM}/{dd}` | Date components (zero-padded) |
| `{model}` | Forecast model ID (see Models section) |
| `{HH}` | Forecast hour (00–23, zero-padded) |
| `{minutesFolder}` | Sub-hourly folder: empty for hour boundaries, `_10`, `_20`, `_30`, `_40`, `_50` otherwise |
| `{layer}` | Layer file identifier (see Layers section) |
| `{yyyyMMdd_HH}` | Compact date-hour, e.g. `20260325_00` |
| `{minutes}` | Same as minutesFolder – appended to filename |

**Example (GFS 2m temperature, 2026-03-25 00Z)**

```
https://data.ventusky.com/2026/03/25/gfs/whole_world/hour_00/gfs_teplota_2_m_20260325_00.jpg
```

**Response**: JPEG image (equirectangular projection, ~1440×721 px for most models)

---

### 4. Regional Tiled Weather Tile (JPEG Image)

Used for high-resolution regional models (HRRR, ICON-DE, ICON-EU, etc.) that
cover a smaller geographic area and are split into tiles.

```
GET https://data.ventusky.com/{yyyy}/{MM}/{dd}/{model}/tilled_world/hour_{HH}{minutesFolder}/{model}_{layer}_{tileX}_{tileY}_{yyyyMMdd_HH}{minutes}.jpg
```

**Additional variables**

| Variable | Description |
|---|---|
| `{tileX}` | Tile column index (starts at 0) |
| `{tileY}` | Tile row index (starts at 0) |

**Example (HRRR temperature tile)**

```
https://data.ventusky.com/2026/03/25/hrrr/tilled_world/hour_00/hrrr_teplota_2_m_0_0_20260325_00.jpg
```

---

### 5. Pressure System Centres JSON

```
GET https://data.ventusky.com/{yyyy}/{MM}/{dd}/{model}/whole_world/hour_{HH}{minutesFolder}/{model}_pressure_low_high_{yyyyMMdd_HH}{minutes}.json
```

**Response**

```json
{
  "l": [[-61.75, -58.5, 950], [66.75, 4.5, 964]],
  "h": [[29.5, 52, 1009], [51.5, 172.25, 1028]]
}
```

- `"l"` = low-pressure centres: `[latitude, longitude, hPa]`
- `"h"` = high-pressure centres: `[latitude, longitude, hPa]`

---

### 6. Weather Fronts JSON

```
GET https://data.ventusky.com/{yyyy}/{MM}/{dd}/{model}/whole_world/hour_{HH}/{model}_fronts_{yyyyMMdd_HH}.json
```

**Response**

```json
{
  "fronts": [
    {
      "type": "occluded",
      "direction": "right",
      "points": [[-14506, 7486], [-14586, 7533], ...]
    },
    {
      "type": "warm",
      "direction": "right",
      "points": [...]
    }
  ]
}
```

Front types: `warm`, `cold`, `occluded`, `stationary`

The `points` are in an internal coordinate system (not lat/lon); they are
integers scaled from the model grid.

---

### 7. Isolines (Isobars, Isotherms, etc.)

```
GET https://data.ventusky.com/{yyyy}/{MM}/{dd}/{model}/whole_world/hour_{HH}/{model}_iso_{type}_{yyyyMMdd_HH}.json
```

> **Note**: Despite the `.json` extension, the server returns `Content-Type: image/png`.
> The response is a custom PNG-encoded binary format used by the Ventusky canvas
> renderer to draw isolines, not a standard image.

**Valid `{type}` values**

| Type | Description |
|---|---|
| `pressure` | Isobars (hPa) |
| `geopotential-300hpa` | 300 hPa geopotential height |
| `geopotential-500hpa` | 500 hPa geopotential height |
| `geopotential-850hpa` | 850 hPa geopotential height |
| `dew` | Dew-point temperature |
| `temperature-2m` | 2 m temperature |
| `temperature-850hpa` | 850 hPa temperature |
| `freezing` | Freezing level |

---

### 8. Hurricane / Tropical Storm Tracks

```
GET https://api.ventusky.com/v2/api.ventusky_hurricane.json.php?end_time_unix={end_ms}&start_time_unix={start_ms}
```

**Parameters**

| Name | Type | Description |
|---|---|---|
| `end_time_unix` | integer | End of time range in **milliseconds** since Unix epoch |
| `start_time_unix` | integer | Start of time range in **milliseconds** since Unix epoch |

**Response**: JSON containing hurricane track data (empty when no active storms).

---

### 9. All Active Webcam IDs

```
GET https://webcams.ventusky.com/update.json
```

**Response**: JSON with key `"actual"` containing a list of integer webcam IDs.

---

### 10. Nearest Webcams

```
GET https://webcams.ventusky.com/api/api.get_nearest_camera.php?lat={lat}&lon={lon}&count={count}
```

**Response** – JSON array

```json
[
  {
    "title": "Pearl Street @ Dover",
    "id": 826034461,
    "lat": 40.7087,
    "lon": -74.0019,
    "source": "511ny.org",
    "q": 0,
    "distance": 0.57
  }
]
```

---

### 11. Webcam Latest Thumbnail

```
GET https://webcams.ventusky.com/data/{idLast2}/{camId}/latest_thumb.jpg?{MMddHHmm}
```

- `{idLast2}` = last 2 digits of the webcam ID (e.g. for ID `826034461` → `61`)
- `{MMddHHmm}` = cache-buster timestamp

**Example**

```
https://webcams.ventusky.com/data/61/826034461/latest_thumb.jpg?03250230
```

---

### 12. Webcam Historical Frame

```
GET https://webcams.ventusky.com/data/{idLast2}/{camId}/{steps}/{yyyyMMdd_HHmm}.jpg
```

---

### 13. Static Base-Map Tiles

Standard OSM slippy-map tile scheme.

```
GET https://static.ventusky.com/tiles/{version}/{layer}/{z}/{x}/{y}.png
```

**Available layers**

| Layer | Version | URL prefix |
|---|---|---|
| Land polygons | v1.1 | `https://static.ventusky.com/tiles/v1.1/land` |
| Country/state borders | v1.0 | `https://static.ventusky.com/tiles/v1.0/border` |
| City labels | v2.2 | `https://static.ventusky.com/tiles/v2.2/cities` |
| Webcam positions | v1.0 | `https://static.ventusky.com/tiles/v1.0/cams` |
| OSM custom | v1.0 | `https://static.ventusky.com/tiles/v1.0/osm_custom` |

**Example (land tile, zoom 4)**

```
https://static.ventusky.com/tiles/v1.1/land/4/8/5.png
```

---

### 14. High-Zoom Map Tiles (Zoom ≥ 13)

```
GET https://map.ventusky.com/tiles/{z}/{x}/{y}.png?256
```

Used at zoom levels 13 and above for detailed street-level map tiles.

**Example**

```
https://map.ventusky.com/tiles/13/2410/3088.png?256
```

---

### 15. WAQI Air Quality (Third-Party Token)

Ventusky uses the WAQI API for the AQI chart overlay. The API token is
embedded directly in the JavaScript bundle.

```
GET https://api.waqi.info/feed/geo:{lat};{lon}/?token=904a1bc6edf77c428347f2fe54cf663bcffaec21
```

---

### 16. Logged-In User Info

Requires authentication. Ventusky uses a cookie-based session.

```
GET https://users.ventusky.com/api/api.logged_user_info.php
```

**Required cookie**: `ventusky_permanent=<session_token>`

Obtain the token by logging in at `https://my.ventusky.com/login/`.

---

## Models

All model identifiers found in the JavaScript source (`ha` variable):

| Identifier | Description |
|---|---|
| `gfs` | NOAA GFS (global, 0.25°) |
| `ecmwf-hres` | ECMWF HRES (global, ~9 km) |
| `ecmwf-mres` | ECMWF MRES (global, ~25 km) |
| `icon` | DWD ICON global (13 km) |
| `icon_eu` | DWD ICON-EU (7 km) |
| `icon_de` | DWD ICON-D2 (2.2 km, Germany) |
| `icon_ch` | MeteoSwiss ICON-CH (~1 km, Switzerland) |
| `kma_um` | Korea KMA Unified Model |
| `gem` | CMC GEM (Canada, 10 km) |
| `hrrr` | NOAA HRRR (3 km, CONUS) |
| `nbm` | NOAA National Blend of Models |
| `nam_us` | NOAA NAM US (12 km) |
| `nam_hawai` | NOAA NAM Hawaii |
| `ukmo` | UK Met Office (global) |
| `ukmo_uk` | UK Met Office (UK, 2 km) |
| `arome` | Météo-France AROME (1.3 km, France) |
| `aladin` | Aladin (France/Czech, 5 km) |
| `meps` | MetCoOp MEPS (2.5 km, Nordic) |
| `harmonie_eu` | Harmonie (European) |
| `harmonie_car` | Harmonie Caribbean |
| `worad` | World Radar composite |
| `worad_hres` | World Radar high-res |
| `eurad` | EU Radar composite |
| `eurad_hres` | EU Radar high-res |
| `usrad` | US Radar composite |
| `earad` | East Asia Radar |
| `silam` | SILAM air quality (global) |
| `silam_eu` | SILAM air quality (Europe) |
| `cams` | Copernicus CAMS air quality |
| `goes` | GOES satellite (global) |
| `goes16` | GOES-16 (Americas) |
| `meteosat_hd` | Meteosat high-definition |
| `meteosat` | Meteosat |
| `himawari` | Himawari (Asia-Pacific) |
| `rtofs` | RTOFS ocean currents (US) |
| `stofs` | STOFS storm surge |
| `stofs_us` | STOFS US |
| `mfwam` | MF-WAM ocean waves |
| `wavewatch_no` | WaveWatch3 (Norway) |
| `smoc` | SMOC ocean currents |

---

## Layers (File Identifiers)

The `{layer}` token in tile URLs is the internal Czech/Slovak file identifier
(the site was originally developed in Czech Republic). The mapping table below
shows the human-readable name → internal file name.

### Temperature

| Layer ID | File Name | Description |
|---|---|---|
| `temperature-water` | `teplota_voda` | Sea surface temperature |
| `temperature-5cm` | `teplota_surface` | 5 cm soil temperature |
| `temperature-2m` | `teplota_2_m` | 2 m air temperature |
| `temperature-anomaly-2m` | `teplota_odchylka_2_m` | 2 m temperature anomaly |
| `temperature-950hpa` | `teplota_95000_pa` | Temperature at 950 hPa |
| `temperature-850hpa` | `teplota_85000_pa` | Temperature at 850 hPa |
| `temperature-700hpa` | `teplota_70000_pa` | Temperature at 700 hPa |
| `temperature-500hpa` | `teplota_50000_pa` | Temperature at 500 hPa |
| `temperature-300hpa` | `teplota_30000_pa` | Temperature at 300 hPa |
| `freezing` | `nulova_izoterma` | Freezing level |
| `feels-like` | `teplota_pocit` | Apparent/feels-like temperature |

### Precipitation & Radar

| Layer ID | File Name | Description |
|---|---|---|
| `rain-1h` | `srazky_1h` | 1-hour precipitation accumulation |
| `rain-3h` | `srazky_3h` | 3-hour precipitation accumulation |
| `rain-ac` | `srazky_ac` | Total accumulation from run start |
| `precipitation-anomaly` | `srazky_odchylka` | Precipitation anomaly |
| `radar` | `srazky_dbz` | Radar reflectivity (dBZ) |
| `satellite` | `rgba` | Satellite imagery (RGBA composite) |

### Clouds

| Layer ID | File Name | Description |
|---|---|---|
| `clouds-total` | `oblacnost` | Total cloud cover |
| `clouds-low` | `oblacnost_low` | Low-level clouds |
| `clouds-middle` | `oblacnost_middle` | Mid-level clouds |
| `clouds-high` | `oblacnost_high` | High-level clouds |
| `cloud-base` | `cloud_base` | Cloud base height |
| `visibility` | `visibility` | Surface visibility |

### Wind

| Layer ID | File Name | Description |
|---|---|---|
| `wind-10m` | `vitr_u_10_m` | 10 m wind (U component; V = `vitr_v_10_m`) |
| `wind-100m` | `vitr_u_100_m` | 100 m wind |
| `wind-850hpa` | `vitr_u_85000_pa` | Wind at 850 hPa |
| `wind-500hpa` | `vitr_u_50000_pa` | Wind at 500 hPa |
| `gust` | `vitr_naraz` | Wind gust |
| `gust-ac` | `vitr_naraz_ac` | Maximum gust accumulation |

### Pressure / Geopotential

| Layer ID | File Name | Description |
|---|---|---|
| `pressure` | `tlak` | Mean sea-level pressure |
| `geopotential-850hpa` | `gph_850` | 850 hPa geopotential |
| `geopotential-500hpa` | `gph_500` | 500 hPa geopotential |
| `geopotential-300hpa` | `gph_300` | 300 hPa geopotential |

### Storm Indices

| Layer ID | File Name | Description |
|---|---|---|
| `cape` | `cape` | CAPE (J/kg) |
| `cape-shear` | `cape_shear` | CAPE with shear |
| `shear` | `shear` | Wind shear |
| `hail-probability` | `hail_probability` | Hail probability |
| `cin` | `cin` | Convective inhibition |
| `li` | `li` | Lifted index |
| `helicity` | `helicity` | Storm-relative helicity |

### Humidity

| Layer ID | File Name | Description |
|---|---|---|
| `humidity-2m` | `vlhkost` | 2 m relative humidity |
| `humidity-850hpa` | `vlhkost_85000_pa` | 850 hPa relative humidity |
| `dew` | `dew_point` | Dew-point temperature |

### Ocean / Sea

| Layer ID | File Name | Description |
|---|---|---|
| `wave` | `swh` | Significant wave height (total) |
| `wind-wave` | `shww` | Significant wind-wave height |
| `swell` | `shts` | Swell height |
| `currents` | `proud_u` | Ocean surface currents (U; V = `proud_v`) |
| `tide` | `tide` | Tide height |
| `tide-surge` | `tide_surge` | Storm surge |

### Snow

| Layer ID | File Name | Description |
|---|---|---|
| `snow` | `snih` | Snow depth |
| `snow-new-ac` | `novy_snih_ac` | New snow accumulation |

### Air Quality

| Layer ID | File Name | Description |
|---|---|---|
| `pm25` | `pm25` | PM2.5 concentration |
| `pm10` | `pm10` | PM10 concentration |
| `no2` | `no2` | NO2 concentration |
| `so2` | `so2` | SO2 concentration |
| `o3` | `o3` | Ozone concentration |
| `dust` | `dust` | Dust/aerosol |
| `co` | `co` | Carbon monoxide |
| `aqi` | `aqi` | Air Quality Index |
| `uv` | `uv` | UV index |

---

## Python Client Usage

See `ventusky_client.py` for the full implementation. Quick examples:

```python
from ventusky_client import VentuskyClient, LAYER_FILES
from datetime import datetime, timezone

client = VentuskyClient()
t = datetime(2026, 3, 25, 0, 0, tzinfo=timezone.utc)

# Search cities
results = client.search_city("Berlin")

# Get weather tile (GFS 2m temperature)
img = client.get_weather_tile("gfs", "teplota_2_m", t)
with open("temperature.jpg", "wb") as f:
    f.write(img)

# Get pressure H/L positions
pressure = client.get_pressure_systems("gfs", t)
for low in pressure["l"][:3]:
    print(f"Low at {low[0]:.1f}N {low[1]:.1f}E: {low[2]} hPa")

# Get weather fronts
fronts = client.get_weather_fronts("gfs", t)

# Find nearby webcams
cams = client.get_nearest_webcams(lat=51.5074, lon=-0.1278, count=5)

# Download map tile
tile = client.get_static_tile("land", z=5, x=15, y=10)

# Build URL without downloading
url = client.build_weather_tile_url("ecmwf-hres", "srazky_1h", t)
print(url)
```

---

## Caching

All data tiles include a `Cache-Control: max-age=21600, public` header
(6-hour cache). The `?{cache}` parameter seen in the JavaScript URL templates
is a timestamp/version number appended to bust the CDN cache when model data
is updated. For most use cases it can be omitted.

---

## Rate Limiting / Authentication

- No API key is required for tile and data endpoints.
- Tiles are served via Cloudflare CDN.
- Premium features (e.g., ECMWF HRES data, higher resolution models) may
  require a paid account accessed via the `ventusky_permanent` cookie.
- Be respectful: do not issue hundreds of simultaneous requests.
