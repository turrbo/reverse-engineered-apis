# Pivotal Weather API - Reverse Engineering Notes

**Reversed on:** 2026-03-25
**Method:** Browser network interception (XHR/Fetch monitoring + DOM inspection)
**Target:** https://www.pivotalweather.com

---

## Overview

Pivotal Weather is a professional meteorological site providing access to numerical weather prediction (NWP) model outputs, ensemble forecasts, observations, and severe weather data. The site uses a PHP backend with jQuery-driven AJAX calls.

**Security:** The site is protected by AWS WAF with a JavaScript challenge mechanism. Static HTTP requests (curl without browser execution) receive a 403 or a WAF challenge page. Browser sessions that pass the WAF challenge receive session cookies that allow subsequent API access.

---

## Infrastructure

| Domain | Purpose |
|--------|---------|
| `www.pivotalweather.com` | Main application, API endpoints (PHP) |
| `home.pivotalweather.com` | Marketing site / home page (Shopify) |
| `m1o.pivotalweather.com` | **Model forecast map image server** |
| `x-hv1.pivotalweather.com` | **Analysis/observation map image server** |

---

## Discovered API Endpoints

### 1. GET /latest_models.php

Returns JSON with the latest available model run information for all models.

**URL:** `https://www.pivotalweather.com/latest_models.php`

**Response shape:**
```json
{
  "gfs": {"rh": "2026032418", "fh": 384, "fh_final": 384},
  "ecmwf_full": {"rh": "2026032412", "fh": 144, "fh_final": 360},
  "hrrr": {"rh": "2026032501", "fh": 18, "fh_final": 48},
  ...
}
```

**Fields:**
- `rh`: Run hour in `YYYYMMDDHH` format (UTC)
- `fh`: Latest forecast hour currently available
- `fh_final`: Final forecast hour for the complete run

---

### 2. GET /latest_runs.php

Compact run-status endpoint used for polling. Returns similar data to `/latest_models.php`.

**URL:** `https://www.pivotalweather.com/latest_runs.php`

---

### 3. GET /status_model.php

Returns detailed availability status for a specific model (which forecast hours have been processed).

**URL:** `https://www.pivotalweather.com/status_model.php?m={model}`
**URL (with soundings):** `https://www.pivotalweather.com/status_model.php?m={model}&s=1`

**Parameters:**
- `m` (required): Model name in lowercase (e.g., `gfs`, `hrrr`, `nam`)
- `s` (optional): Set to `1` to include sounding availability data

**Response:** JSON mapping forecast hours to availability booleans/status values.

This endpoint is polled every 20 seconds by the model viewer page while a run is being processed.

---

### 4. Model Map Images (m1o.pivotalweather.com)

This is the most important API - direct access to forecast map PNG images.

**URL Pattern:**
```
https://m1o.pivotalweather.com/maps/models/{model}/{init_time}/{fhr_padded}/{parameter}.{region}.png
```

**Thumbnail version:**
```
https://m1o.pivotalweather.com/maps/models/{model}/{init_time}/{fhr_padded}/thumbs/{parameter}.{region}.png
```

**Parameters:**
- `{model}`: Lowercase model name (e.g., `gfs`, `ecmwf_full`, `hrrr`, `gefsens`)
- `{init_time}`: Run initialization time in `YYYYMMDDHH` format (UTC), e.g., `2026032418`
- `{fhr_padded}`: Forecast hour zero-padded to 3 digits, e.g., `024` for 24h
- `{parameter}`: Weather field name (see Parameters section below)
- `{region}`: Geographic region code (see Regions section below)

**Confirmed examples:**
```
https://m1o.pivotalweather.com/maps/models/gfs/2026032418/006/prateptype_cat-imp.conus.png
https://m1o.pivotalweather.com/maps/models/gfs/2026032418/024/sfctemp-imp.conus.png
https://m1o.pivotalweather.com/maps/models/ecmwf_full/2026032412/120/1000-500_thick.conus.png
https://m1o.pivotalweather.com/maps/models/hrrr/2026032500/006/sfctemp-imp.conus.png
https://m1o.pivotalweather.com/maps/models/gefsens/2026032418/120/sfctemp-imp.conus.png
```

---

### 5. Analysis/Observation Maps (x-hv1.pivotalweather.com)

Static analysis and observation maps from various data sources.

**URL Pattern:**
```
https://x-hv1.pivotalweather.com/maps/{product_path}/{filename}.{region}.png
```

**Confirmed URLs:**
```
https://x-hv1.pivotalweather.com/maps/warnings/nwshaz.conus.png
https://x-hv1.pivotalweather.com/maps/warnings/thumbs/nwshaz.conus.png
https://x-hv1.pivotalweather.com/maps/ndfd/latest/ndfd_sfctmax.conus.png
https://x-hv1.pivotalweather.com/maps/wpc/latest/wpc_qpf_024h_p.conus.png
https://x-hv1.pivotalweather.com/maps/cpc/latest/610temp.conus.png
https://x-hv1.pivotalweather.com/maps/spc/spcd1four_panel.conus.png
https://x-hv1.pivotalweather.com/maps/spc/thumbs/spcd1cat.conus.png
https://x-hv1.pivotalweather.com/maps/mrms/latest/mrms_qpe_006h_p.conus.png
https://x-hv1.pivotalweather.com/maps/stageiv/latest/stageiv_qpe_024h_p.conus.png
https://x-hv1.pivotalweather.com/maps/nohrsc/latest/nohrsc_24hsnow.conus.png
https://x-hv1.pivotalweather.com/maps/rtma_ru/latest/sfct-imp.conus.png
https://x-hv1.pivotalweather.com/maps/rtma_ru/latest/thumbs/sfct-imp.conus.png
```

**Product path patterns:**
- `warnings/` - NWS active warnings and hazards
- `ndfd/latest/` - NDFD (National Digital Forecast Database)
- `wpc/latest/` - Weather Prediction Center products
- `cpc/latest/` - Climate Prediction Center outlooks
- `spc/` - Storm Prediction Center outlooks
- `mrms/latest/` - MRMS multi-radar/sensor QPE
- `stageiv/latest/` - Stage IV QPE analysis
- `nohrsc/latest/` - NOHRSC snow analysis
- `rtma_ru/latest/` - RTMA Real-Time Mesoscale Analysis

---

### 6. Model Viewer Page

**URL:** `https://www.pivotalweather.com/model.php`

**Query Parameters:**
- `model` (string): Model name in UPPERCASE (e.g., `GFS`, `ECMWF`, `HRRR`)
- `fhr` (int): Forecast hour
- `field` (string): Parameter name (same as used in image URLs)
- `reg` (string): Region code
- `rh` (string, optional): Specific run hour `YYYYMMDDHH` - omit for latest

**Example:**
```
https://www.pivotalweather.com/model.php?model=GFS&fhr=24&field=sfctemp-imp&reg=conus
https://www.pivotalweather.com/model.php?model=HRRR&fhr=6&field=prateptype_cat-imp&reg=conus&rh=2026032500
```

---

### 7. Sounding Page

Displays atmospheric sounding profile for a specific model, location, and forecast time.

**URL:** `https://www.pivotalweather.com/sounding.php`

**Query Parameters:**
- `model` (string): Model name in lowercase
- `rh` (string): Run hour `YYYYMMDDHH`
- `fh` (int): Forecast hour
- `lat` (float): Latitude
- `lon` (float): Longitude (negative for western hemisphere)
- `reg` (string): Region code

**Example:**
```
https://www.pivotalweather.com/sounding.php?model=gfs&rh=2026032418&fh=24&lat=39.95&lon=-75.17&reg=conus
```

---

### 8. Maps Page

**URL:** `https://www.pivotalweather.com/maps.php`

**Query Parameters:**
- `p` (string): Map product identifier
- `r` (string): Region code

---

## JavaScript Global State Objects

When the model viewer page is loaded, two key global objects are populated:

### `pw_web_state`

Contains the current page state:
```json
{
  "ajax": {
    "check_display_model_maps": {
      "interval": 20000,
      "url": "/status_model.php?m=gfs"
    },
    "check_display_model_soundings": {
      "interval": 20000,
      "url": "/status_model.php?m=gfs&s=1"
    }
  },
  "display_attributes": {
    "initial": {
      "model": "gfs",
      "region": "conus",
      "rh": "2026032418",
      "fh": 6,
      "parameter": "prateptype_cat-imp"
    }
  },
  "fhs": {
    "all": [0, 3, 6, 9, ..., 384],
    "available": [6, 9, 12, ..., 384],
    "excluded": [0, 3]
  },
  "image_containers": {
    "active_list": [{
      "image_url": "https://m1o.pivotalweather.com/maps/models/gfs/2026032418/006/prateptype_cat-imp.conus.png",
      "model": "gfs",
      "rh": "2026032418",
      "fh": 6,
      "parameter": "prateptype_cat-imp"
    }]
  },
  "tier_ui": "public"
}
```

### `pw_global_data_status`

Contains run availability data for all models:
```json
{
  "models": {
    "runs": {
      "gfs": {
        "2026032200": 384,
        "2026032206": 384,
        ...
        "2026032418": 384
      },
      "hrrr": {
        "2026032318": 48,
        ...
        "2026032501": 18
      }
    },
    "run_tiers": {
      "gfs": {
        "2026032418": ["public", "plus"]
      }
    },
    "latest_run": {
      "gfs": {"rh": "2026032418", "fh": 384, "fh_final": 384},
      "hrrr": {"rh": "2026032501", "fh": 18, "fh_final": 18}
    },
    "ajax": {
      "interval": 60000,
      "url": "latest_models.php"
    }
  }
}
```

---

## Available Models

| Model ID | Name | Provider | Max FHR | Run Cadence |
|----------|------|----------|---------|-------------|
| `gfs` | GFS | NOAA/NCEP | 384h | 00/06/12/18z |
| `aigfs` | AI-GFS | NOAA | 384h | 00/06/12/18z |
| `ecmwf_full` | ECMWF | ECMWF | 360h | 00/12z |
| `ecmwf_aifs` | ECMWF AIFS | ECMWF | 360h | 00/06/12/18z |
| `icon` | ICON | DWD | 180h | 00/06/12/18z |
| `ukmo_global` | UK Met Office | UKMO | 168h | 00/06/12/18z |
| `gdps` | GDPS | Environment Canada | 240h | 00/12z |
| `nam` | NAM | NOAA/NCEP | 84h | 00/06/12/18z |
| `nam4km` | NAM 4km | NOAA/NCEP | 60h | 00/06/12/18z |
| `hrrr` | HRRR | NOAA/NCEP | 48h | Hourly |
| `rap` | RAP | NOAA/NCEP | 51h | Hourly |
| `rdps` | RDPS | Environment Canada | 84h | 00/06/12/18z |
| `hrdps` | HRDPS | Environment Canada | 48h | 00/06/12/18z |
| `rrfs_a` | RRFS-A | NOAA | 84h | 00/06/12/18z |
| `hrwarw` | HRW ARW | NOAA | 48h | 00/12z |
| `hrwfv3` | HRW FV3 | NOAA | 60h | 00/12z |
| `hrwnssl` | HRW NSSL | NOAA/NSSL | 48h | 00/12z |
| `mpas_gsl_g` | MPAS GSL | NOAA/GSL | 84h | 00/12z |
| `mpas_nssl_htpo` | MPAS NSSL HTPO | NOAA/NSSL | 48h | 00/12z |
| `mpas_nssl_rn` | MPAS NSSL Rain | NOAA/NSSL | 84h | 00/12z |
| `gefsens` | GEFS Ensemble | NOAA/NCEP | 840h | 00/06/12/18z |
| `cmceens` | CMC Ensemble | Environment Canada | 384h | 00/12z |
| `epsens` | ECMWF ENS | ECMWF | 360h | 00/12z |
| `epsens_opendata` | ECMWF ENS Open Data | ECMWF | 144h | 00/06/12/18z |
| `eps_aifsens` | ECMWF AIFS ENS | ECMWF | 360h | 00/12z |
| `iconens` | ICON ENS | DWD | 180h | 00/06/12/18z |
| `mogrepsgens` | MOGREPS-G | UKMO | 198h | 00/06/12/18z |
| `srefens` | SREF | NOAA/NCEP | 87h | 03/09/15/21z |
| `cfs` | CFS | NOAA/NCEP | 768h | 00/06/12/18z |

---

## Common Parameters (Fields)

### Surface and Precipitation
| Parameter | Description |
|-----------|-------------|
| `prateptype_cat-imp` | Precipitation Type & Rate (imperial, in/hr) |
| `prateptype_cat-met` | Precipitation Type & Rate (metric, mm/hr) |
| `sfctemp-imp` | 2m Temperature (°F) |
| `sfctemp-met` | 2m Temperature (°C) |
| `sfcdewp-imp` | 2m Dew Point (°F) |
| `sfcrh` | 2m Relative Humidity (%) |
| `sfcwind-imp` | 10m Wind (mph) |
| `sfcwindgust-imp` | 10m Wind Gust (mph) |
| `mslp` | Mean Sea Level Pressure (mb) |
| `cape` | CAPE (J/kg) |
| `cin` | CIN (J/kg) |
| `capecin` | CAPE + CIN combined |
| `liftedindex` | Lifted Index |
| `theta-e` | Theta-E (equivalent potential temperature) |

### Upper Air
| Parameter | Description |
|-----------|-------------|
| `1000-500_thick` | 1000-500mb Thickness (dam) |
| `500_hgt` | 500mb Geopotential Height (dam) |
| `500_vort` | 500mb Absolute Vorticity |
| `700_hgt` | 700mb Geopotential Height |
| `850_hgt` | 850mb Geopotential Height |
| `850t` | 850mb Temperature |
| `850wind` | 850mb Wind |
| `250wind` | 250mb Wind (Jet Stream) |
| `300wind` | 300mb Wind |

### QPF (Quantitative Precipitation Forecasts)
| Parameter | Description |
|-----------|-------------|
| `qpf3h-imp` | 3-hour QPF (inches) |
| `qpf6h-imp` | 6-hour QPF (inches) |
| `qpf24h-imp` | 24-hour QPF (inches) |
| `snowfall3h-imp` | 3-hour Snowfall (inches) |
| `snowfall6h-imp` | 6-hour Snowfall (inches) |
| `snowfall24h-imp` | 24-hour Snowfall (inches) |
| `snow_depth-imp` | Snow Depth (inches) |

---

## Map Regions

| Region Code | Description |
|-------------|-------------|
| `conus` | Continental United States (default) |
| `namussfc` | North America |
| `ne` | Northeast US |
| `se` | Southeast US |
| `mw` | Midwest US |
| `gp` | Great Plains |
| `sw` | Southwest US |
| `nw` | Northwest US |
| `alaska` | Alaska |
| `hawaii` | Hawaii |
| `europe` | Europe |
| `global` | Global |
| `al`, `ca`, `tx`, etc. | Individual US states (Pivotal Plus subscribers) |

---

## URL Parameter Mapping

The JavaScript function `attributes_to_params` renames some keys for URL parameters:

| Internal attribute key | URL parameter key |
|------------------------|-------------------|
| `region` | `r` |
| `parameter` | `p` |
| `model` | `m` |
| `dataset` | `ds` |

---

## Subscription Tiers

- **Public (free):** Access to GFS, NAM, HRRR, RAP, ICON, and other free-tier models. All public regions.
- **Pivotal Plus (paid):** Additional models (ECMWF full, some ensemble members), state-level zoom regions, ad-free viewing, early access to new features.

The `run_tiers` field in `pw_global_data_status` shows which runs are available at each tier level:
```json
"run_tiers": {
  "gfs": {
    "2026032418": ["public", "plus"]
  }
}
```

---

## AWS WAF Notes

The site uses AWS WAF with a JavaScript challenge:
- Challenge URL: `https://2626f9f6dc1f.9622e82a.us-east-2.token.awswaf.com/2626f9f6dc1f/5c8fcae5aa31/3cd74057b9a6/challenge.js`
- Non-browser HTTP clients receive a WAF challenge page (empty body, `x-amzn-waf-action: challenge` header)
- A real browser session with cookies can access static image assets directly without re-challenging

**Workaround:** Use the `requests` library with cookies from an authenticated browser session, or use a headless browser (playwright/puppeteer) to obtain WAF session cookies before making API calls.

---

## Python Client Usage

```python
from pivotal_weather_client import PivotalWeatherClient, MODELS, REGIONS

# Create client
client = PivotalWeatherClient()

# Get latest model runs
runs = client.get_latest_models()
print(f"GFS latest run: {runs['gfs']['rh']}")

# Build a model map URL (no HTTP request)
url = client.get_model_map_url(
    model="gfs",
    init_time="2026032418",  # YYYYMMDDHH
    fhr=24,                   # forecast hour
    parameter="prateptype_cat-imp",
    region="conus"
)
# -> "https://m1o.pivotalweather.com/maps/models/gfs/2026032418/024/prateptype_cat-imp.conus.png"

# Download a single map image
image_bytes = client.download_model_map(
    model="gfs",
    init_time="2026032418",
    fhr=24,
    parameter="sfctemp-imp",
    region="conus",
    output_path="/tmp/gfs_sfctemp_f024.png"
)

# Download an analysis map
client.download_analysis_map("stageiv/qpe_024h", output_path="/tmp/stageiv_qpe.png")

# Download a full model loop (animation frames)
paths = client.download_model_loop(
    model="hrrr",
    init_time="2026032500",
    parameter="prateptype_cat-imp",
    region="conus",
    fhr_start=0,
    fhr_end=18,
    fhr_step=1,
    output_dir="/tmp/hrrr_loop"
)

# Get sounding page URL
sounding_url = client.get_sounding_page_url(
    model="gfs",
    init_time="2026032418",
    fhr=24,
    lat=39.95,
    lon=-75.17
)

# Get model viewer page URL
page_url = client.get_model_page_url("GFS", fhr=24, field="sfctemp-imp", region="ne")
```

---

## Key JavaScript Functions Discovered

```javascript
// Build model page URL
function model_page_url(attributes) {
    var url = "model.php";
    return url += "?" + $.param(attributes_to_params(attributes));
}

// Build maps page URL
function maps_page_url(attributes) {
    var url = "maps.php";
    return url += "?" + $.param(attributes_to_params(attributes));
}

// Build sounding page URL
function sounding_page_url(attributes) {
    var url = pw_web_state.soundings_settings.page_url;
    return url += "?" + $.param(attributes_to_params(attributes));
}

// Poll model run progress
function ajax_get_model_progress() {
    $.ajax({type: "GET", url: "latest_runs.php"}).success(function(runs_data) {
        // updates pw_global_data_status.models.runs
    });
}

// Poll map availability for specific model
function ajax_get_latest_fh_maps() {
    var ajax_url = pw_web_state.ajax.check_display_model_maps.url;
    // ajax_url = "/status_model.php?m=gfs"
    $.ajax({url: ajax_url, dataType: "json", cache: false}).done(function(json_data) {
        // updates available forecast hours
    });
}
```

---

## Notes

1. The `/latest_models.php` and `/latest_runs.php` endpoints are the best starting points - they tell you what data is currently available before constructing image URLs.

2. Model image filenames use lowercase model names, but the web page URL uses uppercase model names in the `model=` parameter.

3. Forecast hours are zero-padded to 3 digits in image URLs (e.g., `006`, `024`, `120`) but are plain integers in API JSON responses.

4. The `m1o.pivotalweather.com` subdomain appears to be a CDN-backed image server. Images are served directly as PNG files with no authentication on the image domain itself - the WAF sits at `www.pivotalweather.com`.

5. The `pw_web_state.tier_ui` field indicates the user's subscription level (`"public"` for free users, `"plus"` for subscribers).

6. Some ensemble models (ECMWF, GEFS) have both individual member maps and derived statistics (mean, spread, probability maps) accessible via different parameter names.
