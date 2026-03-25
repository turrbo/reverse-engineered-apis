# SpotWX API — Reverse Engineering Notes & Python Client

SpotWX (https://spotwx.com) is a free weather forecast portal that provides
point forecasts from 20+ NWP models (GFS, HRRR, ECMWF, GDPS, HRDPS, etc.)
for any latitude/longitude. This document captures all discovered internal
API endpoints and explains how to use the Python client.

---

## Architecture Overview

SpotWX is a PHP application that:

1. Accepts lat/lon from the user (via map click or geocoder)
2. Makes multiple XHR calls to PHP scripts to discover available products
3. Opens `grib_index.php` in a new iframe/tab to render Highcharts graphs
4. Embeds the forecast data as JavaScript arrays inside the HTML

There is **no formal JSON API**. All data is embedded as JavaScript inside
returned HTML pages. The client parses this using regular expressions.

---

## Discovered Endpoints

All endpoints are on `https://spotwx.com`.

### 1. `GET /products/spot_info2.php`

Returns an HTML fragment with location timezone info.

```
/products/spot_info2.php?lat=49.25&lon=-123.1
```

Response (HTML fragment):
```
Location: <strong>49.25000 Lat, -123.10000 Lon</strong><br>
Time Zone: America/Vancouver, PDT, UTC -7 hrs
```

---

### 2. `GET /products/spotcatalog_u2.php`

Returns an HTML table listing available products for a location.

```
/products/spotcatalog_u2.php?lat=49.25&lon=-123.1&type=nm&timeunits=t12
```

**Parameters:**

| Parameter  | Required | Values            | Description                         |
|-----------|----------|-------------------|-------------------------------------|
| `lat`      | Yes      | float             | Latitude                            |
| `lon`      | Yes      | float             | Longitude                           |
| `type`     | Yes      | `nm`, `point`, `zone` | Product type to list            |
| `timeunits`| No       | `t12`, `t24`      | 12 or 24 hour time display          |

**`type` values:**
- `nm` — Numerical Weather Models (gridded)
- `point` — Nearest Station Forecasts (SCRIBE, NOWCAST, within 150 km)
- `zone` — Area Forecasts (Meteocode zones)

Response: HTML with `<table>` of product rows, each linking to `grib_index.php`.

---

### 3. `GET /products/grib_polys_u.php`

Returns the NWP grid cell polygon boundaries for all models at a point.
Used to draw colored grid boxes on the map.

```
/products/grib_polys_u.php?lat=49.25&lon=-123.1
```

Response: Colon-separated records, each `>>>` delimited:
```
model_id>>>hex_color>>>WKT_polygon>>>url>>>description
```

Example:
```
gfs_pgrb2_0p25_f>>>#CD853F>>>MULTIPOLYGON(((-123.125 49.125,-123.125 49.375,...)))>>>/products/grib_index.php?model=gfs_pgrb2_0p25_f&lat=49.25&lon=-123.1&tz=-7>>>NOAA<br>GFS (0.25 degree resolution)<br>10 Day Forecast
```

---

### 4. `GET /products/scribe_points_u.php`

Returns the nearest ECCC SCRIBE forecast point.

```
/products/scribe_points_u.php?lat=49.25&lon=-123.1
```

Response: Colon-separated:
```
NAME:TCID:LAT:LON:ELEV_M:DESC1>>>URL1:DESC2>>>URL2:...
```

Example:
```
VANCOUVER HARBOUR:WHC:49.28:-123.12:2:2 Day SCRIBE (based on GEM Regional)>>>/products/grib_index.php?model=scribe_r&tcid=WHC&tz=-7&station=VANCOUVER HARBOUR
```

---

### 5. `GET /products/nowcast_points_u.php`

Returns the nearest ECCC NOWCAST forecast point (12-hour nowcast).

```
/products/nowcast_points_u.php?lat=49.25&lon=-123.1
```

Same format as scribe_points_u.php.

---

### 6. `GET /products/mc_zone_u2.php`

Returns the Meteocode zone identifier for a coordinate.

```
/products/mc_zone_u2.php?lat=49.25&lon=-123.1&range=short
/products/mc_zone_u2.php?lat=49.25&lon=-123.1&range=extended
```

**Parameters:**

| Parameter | Values             | Description                     |
|-----------|--------------------|---------------------------------|
| `lat`     | float              | Latitude                        |
| `lon`     | float              | Longitude                       |
| `range`   | `short`, `extended`| Short-term or extended forecast |

Response: Plain text zone identifier, e.g.:
```
MetroVancouver-centralincludingtheCityofVancouverBurnabyandNewWestminster
```

---

### 7. `GET /products/grib_index.php` (MAIN FORECAST ENDPOINT)

The primary forecast data endpoint. Returns an HTML page containing
embedded Highcharts JavaScript with all forecast data series.

```
/products/grib_index.php?model=gfs_pgrb2_0p25_f&lat=49.25&lon=-123.1&tz=America/Vancouver
```

**Parameters:**

| Parameter | Required | Description |
|-----------|----------|-------------|
| `model`   | Yes      | Model ID (see table below)                                  |
| `lat`     | Yes*     | Latitude (*not needed for station/zone models)             |
| `lon`     | Yes*     | Longitude (*not needed for station/zone models)            |
| `tz`      | Yes      | IANA timezone (e.g., `America/Vancouver`) or UTC offset (e.g., `-7`) |
| `label`   | No       | Custom location label                                        |
| `display` | No       | `table` to get tabular HTML instead of charts               |
| `tcid`    | No       | Station ID for SCRIBE/NOWCAST models (e.g., `WHC`, `YVR`)  |
| `station` | No       | Station name for SCRIBE models                              |
| `zone`    | No       | Zone ID for Meteocode (e.g., `rv7.1`)                      |
| `title`   | No       | Product title for Meteocode (e.g., `FPVR11`)               |

**Tabular mode** (`?display=table`):

Returns an HTML page with a JavaScript variable `aDataSet` containing rows
of CSV-like data, and `columns` defined in DataTables config.

---

## Unit System (Cookie-Based)

Units are controlled via HTTP cookies. Set them on your session to receive
data in your preferred units.

| Cookie       | Default | Options                        | Description             |
|-------------|---------|--------------------------------|-------------------------|
| `tmpunits`   | `C`     | `C`, `F`, `K`                  | Temperature units       |
| `windunits`  | `kph`   | `kph`, `mph`, `kn`, `ms`       | Wind speed units        |
| `pcpunits`   | `mm`    | `mm`, `in`, `kg`               | Precipitation units     |
| `presunits`  | `mb`    | `mb`, `hPa`, `kPa`, `inHg`, `mmHg` | Pressure units     |
| `altunits`   | `m`     | `m`, `ft`                      | Altitude units          |
| `distunits`  | `km`    | `km`, `mi`, `NM`               | Distance units          |
| `timeunits`  | `t12`   | `t12`, `t24`                   | Time format             |

---

## Available Models

### ECCC (Environment and Climate Change Canada)

| Model ID             | Label               | Resolution | Forecast Length |
|---------------------|---------------------|------------|-----------------|
| `hrdps_1km_west`     | HRDPS 1km West      | 1 km       | 2 days          |
| `hrdps_continental`  | HRDPS Continental   | 2.5 km     | 2 days          |
| `rdps_10km`          | RDPS                | 10 km      | 3.5 days        |
| `gdps_15km`          | GDPS                | 15 km      | 10 days         |
| `geps_0p5_raw`       | GEPS (Ensemble)     | 0.5 deg    | 16 days         |

### ECMWF

| Model ID              | Label                | Resolution | Forecast Length |
|----------------------|----------------------|------------|-----------------|
| `ecmwf_ifs`           | ECMWF IFS            | 0.25 deg   | 15 days         |
| `ecmwf_aifs_single`   | ECMWF AIFS (AI)      | 0.25 deg   | 15 days         |

### NOAA (USA)

| Model ID            | Label           | Resolution | Forecast Length          |
|--------------------|-----------------|------------|--------------------------|
| `hrrr_wrfprsf`      | HRRR            | 3 km       | 18 hr (48 hr every 6 hr) |
| `rap_awp130pgrbf`   | RAP             | 13 km      | 21 hr                    |
| `nam_awphys`        | NAM             | 12 km      | 3.5 days                 |
| `sref_pgrb132`      | SREF (Ensemble) | 16 km      | 87 hr                    |
| `gfs_pgrb2_0p25_f`  | GFS             | 0.25 deg   | 10 days                  |
| `gfs_uv`            | GFS UV Index    | 0.5 deg    | 5 days                   |

### ECCC Station-Based (require `tcid` parameter)

| Model ID        | Label                              | Notes                     |
|---------------|-------------------------------------|---------------------------|
| `scribe_r`     | SCRIBE Regional (RDPS-based)        | 3.5-day, needs tcid       |
| `scribe_g`     | SCRIBE Global (GDPS-based)          | 3.5-day, needs tcid       |
| `scribe_x`     | Extended SCRIBE (GDPS extended)     | 4-6 day, needs tcid       |
| `scribe_hybrid`| SCRIBE Hybrid                       | needs tcid                |
| `nwcstg`       | SCRIBE NOWCAST                      | 12-hr, needs tcid         |

### Zone-Based (require `zone` + `title` parameters)

| Model ID    | Label                   | Notes                            |
|------------|-------------------------|----------------------------------|
| `meteocode` | Meteocode (Short/Extended) | Needs zone + title params      |

---

## Data Format: Highcharts Series (chart mode)

In the default chart view, data is embedded as JavaScript:

```javascript
// Simple format
[Date.UTC(2026, 2, 24, 11, 00), 5.4],
[Date.UTC(2026, 2, 24, 12, 00), 5.8],

// Extended format (with description)
{x: Date.UTC(2026, 2, 24, 11, 00), y: 3, desc: 'Very low'},
```

Note: `Date.UTC` month is **0-indexed** (so month 2 = March).

Each series looks like:
```javascript
{
  name: 'Temp.',
  type: 'spline',
  data: [
    [Date.UTC(2026, 2, 24, 11, 00), 5.4],
    ...
  ]
}
```

---

## Data Format: Tabular Mode

In tabular mode (`?display=table`), data is in `aDataSet`:

```javascript
aDataSet = [
  ['2026/03/24 11:00','2026/03/24','11:00','5.4','93','9','054','20','0.0','100','1006.5','','0.0',...],
  ...
];
```

Column definitions are in the DataTables config as `sTitle` entries.

### Typical Columns (GFS)

| Column    | Description                            | Units (default) |
|-----------|----------------------------------------|-----------------|
| DATETIME  | Local datetime                         | string          |
| DATE      | Local date                             | string          |
| TIME      | Local time                             | string          |
| TMP       | 2m temperature                         | °C              |
| RH        | Relative humidity                      | %               |
| WS        | 10m wind speed                         | kph             |
| WD        | 10m wind direction                     | degrees         |
| WG        | Wind gusts                             | kph             |
| APCP      | Accumulated precipitation (cumulative) | mm              |
| CLOUD     | Total cloud cover                      | %               |
| SLP       | Sea-level pressure                     | mb              |
| PTYPE     | Precip type (RA/SN/ZR/IP/blank)        | string          |
| RQP       | Rain quantity (cumulative)             | mm              |
| SQP       | Snow quantity (cumulative)             | mm              |
| FQP       | Freezing rain quantity (cumulative)    | mm              |
| IQP       | Ice pellet quantity (cumulative)       | mm              |
| WS925     | 925 hPa wind speed                     | kph             |
| WD925     | 925 hPa wind direction                 | degrees         |
| TMP850    | 850 hPa temperature                    | °C              |
| WS850     | 850 hPa wind speed                     | kph             |
| WD850     | 850 hPa wind direction                 | degrees         |
| 4LFTX     | Best 4-layer Lifted Index              | K               |
| HGT_0C_DB | Height of 0°C dry bulb level           | m               |
| TMP_SFC   | Surface temperature                    | °C              |
| DSWRF     | Downward shortwave radiation           | W/m2            |
| USWRF     | Upward shortwave radiation             | W/m2            |
| DLWRF     | Downward longwave radiation            | W/m2            |
| ULWRF     | Upward longwave radiation              | W/m2            |

---

## Python Client Usage

### Installation

```bash
pip install requests
```

The client has no other dependencies beyond the Python standard library and `requests`.

### Basic Usage

```python
from spotwx_client import SpotWXClient, Models, TempUnits, WindUnits

# Create client (default: Celsius, kph wind, mm precip)
client = SpotWXClient()

# Get location info
info = client.get_spot_info(lat=49.25, lon=-123.1)
print(info["html"])
# -> Location: 49.25000 Lat, -123.10000 Lon
#    Time Zone: America/Vancouver, PDT, UTC -7 hrs

# List available models at a location
models = client.list_models(lat=49.25, lon=-123.1)
for m in models:
    print(m["model"], m["label"], m["description"])
```

### Fetch Forecast Data (Chart Series Format)

```python
# Returns all data series as dicts with datetime objects
forecast = client.get_forecast(
    model=Models.GFS,
    lat=49.25,
    lon=-123.1,
    tz="America/Vancouver",
)

print(f"Model date: {forecast['model_date']}")
print(f"Model elevation: {forecast['model_elevation']}")

for series in forecast["series"]:
    print(f"\n{series['name']}:")
    for point in series["data"][:3]:
        print(f"  {point['datetime']}  ->  {point['value']}")
```

### Fetch Forecast Data (Tabular Format)

```python
# Tabular format — easier for pandas/CSV
table = client.get_forecast_table(
    model=Models.GFS,
    lat=49.25,
    lon=-123.1,
    tz="America/Vancouver",
)

# As pandas DataFrame
import pandas as pd
df = pd.DataFrame(table["rows"], columns=table["columns"])
print(df.head())
```

### Change Units

```python
client = SpotWXClient(
    temp_units=TempUnits.FAHRENHEIT,   # "F"
    wind_units=WindUnits.MPH,           # "mph"
    precip_units="in",                  # inches
    pressure_units="inHg",
    alt_units="ft",
)

table = client.get_forecast_table(
    model=Models.HRRR,
    lat=39.74,
    lon=-104.98,
    tz="America/Denver",
)
```

### Fetch SCRIBE Station Forecast

```python
# First, find the nearest SCRIBE point
scribe = client.get_nearest_scribe_point(lat=49.25, lon=-123.1)
print(f"Nearest: {scribe['name']} ({scribe['tcid']}) at {scribe['lat']}, {scribe['lon']}")

# Then fetch forecast for that station
forecast = client.get_scribe_forecast(
    tcid=scribe["tcid"],
    tz="America/Vancouver",
    model=Models.SCRIBE_REGIONAL,
)

for series in forecast["series"]:
    print(series["name"], series["data"][0])
```

### Fetch NOWCAST

```python
nowcast_pt = client.get_nearest_nowcast_point(lat=49.25, lon=-123.1)
forecast = client.get_nowcast_forecast(
    tcid=nowcast_pt["tcid"],
    tz="America/Vancouver",
)
```

### Fetch Meteocode Zone Forecast

```python
forecast = client.get_meteocode_forecast(
    lat=49.25,
    lon=-123.1,
    tz="America/Vancouver",
    range="short",  # or "extended"
)
```

### Multi-Model Comparison

```python
# Fetch all available models at once (for comparison)
comparison = client.get_multi_model_comparison(
    lat=49.25,
    lon=-123.1,
    tz="America/Vancouver",
)

for model_id, data in comparison["models"].items():
    if "error" in data:
        print(f"{model_id}: ERROR - {data['error']}")
        continue
    temp_series = next((s for s in data["series"] if "Temp" in s["name"]), None)
    if temp_series:
        first = temp_series["data"][0]
        print(f"{model_id:25}: {first['datetime']} -> {first['value']}°")
```

### Fetch Everything at a Location

```python
# Discover and fetch ALL available products
everything = client.get_all_available_forecasts(
    lat=49.25,
    lon=-123.1,
    tz="America/Vancouver",
    include_station=True,
    include_zone=True,
)

print(f"Numerical models: {len(everything['numerical_models'])}")
print(f"Station forecasts: {len(everything['station_forecasts'])}")
print(f"Zone forecasts: {len(everything['zone_forecasts'])}")
```

### Convert Series to Flat Dict (for Pandas)

```python
forecast = client.get_forecast(Models.GFS, lat=49.25, lon=-123.1)
flat = client.series_to_dict(forecast["series"])
# flat = {"datetime": [...], "Temp.": [...], "RH": [...], ...}

import pandas as pd
df = pd.DataFrame(flat)
df = df.set_index("datetime")
print(df[["Temp.", "RH", "10m Wind"]].head(10))
```

### Grid Polygon Data

```python
# Get grid cell boundaries (useful for map overlays)
polys = client.get_grid_polygons(lat=49.25, lon=-123.1)
for p in polys:
    print(f"{p['model']}: {p['color']} - {p['polygon_wkt'][:50]}...")
```

---

## Command-Line Interface

The client includes a CLI for quick use:

```bash
# List available models
python3 spotwx_client.py list-models 49.25 -123.1

# Get location info
python3 spotwx_client.py info 49.25 -123.1

# Fetch GFS forecast as CSV (stdout)
python3 spotwx_client.py forecast gfs_pgrb2_0p25_f 49.25 -123.1 --tz America/Vancouver

# Fetch HRRR with imperial units
python3 spotwx_client.py forecast hrrr_wrfprsf 39.74 -104.98 \
  --tz America/Denver --units-temp F --units-wind mph --units-precip in

# Fetch forecast as JSON series
python3 spotwx_client.py series gfs_pgrb2_0p25_f 49.25 -123.1 --tz America/Vancouver
```

---

## Geographic Availability of Models

| Model               | Coverage                    |
|--------------------|-----------------------------|
| GFS                 | Global                      |
| GDPS                | Global                      |
| GEPS                | Global                      |
| ECMWF IFS           | Global                      |
| ECMWF AIFS          | Global                      |
| HRDPS 1km West      | Western Canada only          |
| HRDPS Continental   | North America (ECCC domain)  |
| RDPS                | North America (ECCC domain)  |
| HRRR                | CONUS + Alaska               |
| RAP                 | North America                |
| NAM                 | North America                |
| SREF                | North America                |
| SCRIBE/NOWCAST      | Canada only (station-based)  |
| Meteocode           | Canada only (zone-based)     |

---

## Important Notes

1. **No official API** — SpotWX has no documented public API. All endpoints
   are internal and may change without notice.

2. **Rate limiting** — SpotWX does not appear to enforce strict rate limits,
   but please be respectful and do not hammer the server.

3. **Units are cookie-driven** — The server reads cookies to determine units.
   The client handles this automatically.

4. **Timezone handling** — The `tz` parameter controls the local time axis
   on charts/tables. Both IANA names (`America/Vancouver`) and UTC offsets
   (`-7`) are accepted.

5. **Model availability varies by location** — Not all models cover all
   regions. Use `list_models()` to discover what is available at your target
   coordinate.

6. **Data freshness** — Model data is updated as new NWP runs become
   available. The model run time is shown in the page subtitle and returned
   in the `model_date` field.

7. **Authentication** — Most features are available without logging in. The
   login system (`loginck_pdo.php`) appears to enable saved favorites only.

---

## Endpoint Summary Table

| Path                              | Method | Auth | Description                          |
|----------------------------------|--------|------|--------------------------------------|
| `/products/spot_info2.php`        | GET    | No   | Timezone/location info               |
| `/products/spotcatalog_u2.php`    | GET    | No   | List available products              |
| `/products/grib_polys_u.php`      | GET    | No   | Grid polygon boundaries              |
| `/products/scribe_points_u.php`   | GET    | No   | Nearest SCRIBE station               |
| `/products/nowcast_points_u.php`  | GET    | No   | Nearest NOWCAST station              |
| `/products/mc_zone_u2.php`        | GET    | No   | Meteocode zone identifier            |
| `/products/grib_index.php`        | GET    | No   | Main forecast data (chart/table)     |
| `/favorites_pdo.php`              | GET    | Yes  | Add to favorites (requires login)    |
| `/settz.php`                      | GET    | No   | Timezone preference page             |
| `/setunits.html`                  | GET    | No   | Units preference page                |
| `/loginck_pdo.php`                | POST   | -    | Login handler                        |
| `/gisdata/meteocode_zones_611/kml/{zone}.kml` | GET | No | Meteocode zone KML polygon |
