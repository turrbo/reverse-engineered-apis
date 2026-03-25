# Open-Meteo API Reverse Engineering Report

**Date:** 2026-03-25
**Source analyzed:** https://open-meteo.com / https://github.com/open-meteo/open-meteo

---

## Summary

Open-Meteo is a free, open-source weather API that exposes far more functionality than its public documentation covers. By analyzing the open-source Swift server code at https://github.com/open-meteo/open-meteo, we discovered all internal routes, models, parameters, and response formats.

---

## All API Endpoints

### Primary (Documented)

| Endpoint | Base URL | Description |
|----------|----------|-------------|
| `forecast` | `api.open-meteo.com/v1/forecast` | 7-16 day forecast, current weather, all models |
| `archive` | `archive-api.open-meteo.com/v1/archive` | ERA5 reanalysis since 1940 |
| `era5` | `archive-api.open-meteo.com/v1/era5` | ERA5 alias |
| `ensemble` | `ensemble-api.open-meteo.com/v1/ensemble` | Ensemble forecasts |
| `seasonal` | `seasonal-api.open-meteo.com/v1/seasonal` | Seasonal (6-month) forecasts |
| `marine` | `marine-api.open-meteo.com/v1/marine` | Wave and ocean data |
| `air-quality` | `air-quality-api.open-meteo.com/v1/air-quality` | CAMS air quality |
| `climate` | `climate-api.open-meteo.com/v1/climate` | CMIP6 projections 1950-2050 |
| `flood` | `flood-api.open-meteo.com/v1/flood` | GloFas river discharge |
| `elevation` | `api.open-meteo.com/v1/elevation` | DEM elevation lookup |
| `geocoding` | `geocoding-api.open-meteo.com/v1/search` | Location search |

### Model-Specific Forecast Shortcuts

| Endpoint | URL | Default Model |
|----------|-----|---------------|
| `dwd-icon` | `api.open-meteo.com/v1/dwd-icon` | `icon_seamless` |
| `gfs` | `api.open-meteo.com/v1/gfs` | `gfs_seamless` |
| `ecmwf` | `api.open-meteo.com/v1/ecmwf` | `ecmwf_ifs025` |
| `meteofrance` | `api.open-meteo.com/v1/meteofrance` | `meteofrance_seamless` |
| `jma` | `api.open-meteo.com/v1/jma` | `jma_seamless` |
| `metno` | `api.open-meteo.com/v1/metno` | `metno_nordic` |
| `gem` | `api.open-meteo.com/v1/gem` | `gem_seamless` |
| `cma` | `api.open-meteo.com/v1/cma` | `cma_grapes_global` |
| `bom` | `api.open-meteo.com/v1/bom` | `bom_access_global` |

### Undocumented / Semi-Documented Endpoints Discovered

| Endpoint | Base URL | Notes |
|----------|----------|-------|
| **historical-forecast** | `historical-forecast-api.open-meteo.com/v1/forecast` | Archived actual model forecasts (not reanalysis) since 2016 |
| **previous-runs** | `previous-runs-api.open-meteo.com/v1/forecast` | Compare current vs previous model runs |
| **single-runs** | `single-runs-api.open-meteo.com/v1/forecast` | Query specific model initialization times; requires `&run=` |
| **satellite** | `satellite-api.open-meteo.com/v1/archive` | Satellite-derived solar radiation since 1983 |
| **geocoding get** | `geocoding-api.open-meteo.com/v1/get` | Get location by GeoNames integer ID |

### Commercial API Endpoints (Require `&apikey=`)

All free endpoints have `customer-` prefixed commercial equivalents:
- `customer-api.open-meteo.com`
- `customer-archive-api.open-meteo.com`
- `customer-historical-forecast-api.open-meteo.com`
- `customer-previous-runs-api.open-meteo.com`
- `customer-single-runs-api.open-meteo.com`
- `customer-satellite-api.open-meteo.com`
- `customer-ensemble-api.open-meteo.com`
- `customer-seasonal-api.open-meteo.com`
- `customer-marine-api.open-meteo.com`
- `customer-air-quality-api.open-meteo.com`
- `customer-climate-api.open-meteo.com`
- `customer-flood-api.open-meteo.com`

---

## All Query Parameters (Undocumented Ones Highlighted)

### Common Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `latitude` | float or csv | Location latitude (comma-separated for batch) |
| `longitude` | float or csv | Location longitude (comma-separated for batch) |
| `elevation` | float or csv | Override elevation (meters) |
| `location_id` | int or csv | Query by GeoNames location ID |
| `timezone` | string | Timezone name or `auto` |
| `temperature_unit` | string | `celsius` (default), `fahrenheit` |
| `windspeed_unit` / `wind_speed_unit` | string | `kmh` (default), `mph`, `kn`, `ms` |
| `precipitation_unit` | string | `mm` (default), `inch` |
| `length_unit` | string | `metric` (default), `imperial` |
| `timeformat` | string | `iso8601` (default), `unixtime` |
| `format` | string | `json` (default), `csv`, `xlsx`, `flatbuffers` |
| `models` | string or csv | Model selection |
| `cell_selection` | string | `land` (default for forecast), `sea` (default for marine), `nearest` |
| `apikey` | string | Commercial API key |

### Time Range Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `forecast_days` | int | Number of forecast days (1-16 for standard) |
| `past_days` | int | Number of past days to include |
| `start_date` | string | ISO date `YYYY-MM-DD` |
| `end_date` | string | ISO date `YYYY-MM-DD` |
| `past_hours` | int | **[less documented]** Past hours to include |
| `forecast_hours` | int | **[less documented]** Forecast hours to include |
| `initial_hours` | int | **[undocumented]** Start hour offset for `forecast_hours` |
| `start_hour` | string | **[undocumented]** Precise hourly range start `YYYY-MM-DDTHH:MM` |
| `end_hour` | string | **[undocumented]** Precise hourly range end `YYYY-MM-DDTHH:MM` |
| `past_minutely_15` | int | **[undocumented]** Past 15-min intervals |
| `forecast_minutely_15` | int | **[undocumented]** Forecast 15-min intervals |
| `start_minutely_15` | string | **[undocumented]** Precise minutely range start |
| `end_minutely_15` | string | **[undocumented]** Precise minutely range end |
| `initial_minutely_15` | int | **[undocumented]** Minutely offset for `forecast_minutely_15` |
| `run` | string | **[undocumented]** Specific model run time for single-runs-api |

### Variable Selection Parameters

| Parameter | Description |
|-----------|-------------|
| `current` | Current weather variables |
| `hourly` | Hourly variables |
| `daily` | Daily aggregated variables |
| `minutely_15` | 15-minute resolution variables (GFS, ICON-D2, AROME support) |
| `weekly` | **[semi-undocumented]** Weekly aggregated variables (seasonal API) |
| `monthly` | **[semi-undocumented]** Monthly aggregated variables (seasonal API) |
| `six_hourly` | **[undocumented]** 6-hourly aggregation for seasonal |
| `current_weather` | **[legacy]** Boolean, returns `current_weather` block (deprecated in favor of `current`) |

### Advanced Parameters

| Parameter | Description |
|-----------|-------------|
| `bounding_box` | **[semi-undocumented]** `min_lat,min_lon,max_lat,max_lon` - returns all grid cells in box |
| `temporal_resolution` | **[less documented]** Override output resolution: `native`, `hourly`, `hourly_1`, `hourly_3`, `hourly_6` |
| `tilt` | **[undocumented]** Solar panel tilt angle (0-90°) for `global_tilted_irradiance` |
| `azimuth` | **[undocumented]** Solar panel azimuth (0=south, -90=east, 90=west) for GTI |
| `disable_bias_correction` | **[undocumented]** Boolean, skip ERA5 bias correction in climate API |
| `ensemble` | **[undocumented]** Boolean, enable 51 ensemble members for flood `river_discharge` |
| `domains` | Air quality API: `auto`, `global`, `europe` (alternate to `models`) |
| `location_information` | `section` (default), `omit` - control location metadata in output |

---

## All Weather Models

### Forecast Models

| Category | Models |
|----------|--------|
| **Auto/Best-match** | `best_match` |
| **GFS/NCEP** | `gfs_seamless`, `gfs_global`, `gfs025`, `gfs05`, `gfs013`, `gfs_hrrr`, `gfs_graphcast025` |
| **NCEP (explicit prefix)** | `ncep_seamless`, `ncep_gfs_global`, `ncep_nbm_conus`, `ncep_gfs025`, `ncep_gfs013`, `ncep_hrrr_conus`, `ncep_hrrr_conus_15min`, `ncep_nam_conus` |
| **NCEP AI models** | `ncep_aigfs025`, `ncep_aigefs025`, `ncep_gfs_graphcast025` (AI-GFS experimental) |
| **MeteoFrance** | `meteofrance_seamless`, `meteofrance_arpege_seamless`, `meteofrance_arpege_world`, `meteofrance_arpege_europe`, `meteofrance_arpege_world025`, `meteofrance_arome_seamless`, `meteofrance_arome_france`, `meteofrance_arome_france0025`, `meteofrance_arome_france_hd`, `meteofrance_arome_france_hd_15min`, `meteofrance_arome_france_15min` |
| **ECMWF** | `ecmwf_ifs025`, `ecmwf_ifs04`, `ecmwf_aifs025` (AI-IFS), `ecmwf_aifs025_single`, `ecmwf_ifs`, `ecmwf_ifs_analysis`, `ecmwf_ifs_analysis_long_window`, `ecmwf_ifs_long_window`, `ecmwf_wam` |
| **DWD ICON** | `icon_seamless`, `icon_global`, `icon_eu`, `icon_d2`, `dwd_icon_seamless`, `dwd_icon_global`, `dwd_icon`, `dwd_icon_eu`, `dwd_icon_d2`, `dwd_icon_d2_15min` |
| **JMA** | `jma_seamless`, `jma_msm`, `jma_gsm` |
| **GEM/CMC** | `gem_seamless`, `gem_global`, `gem_regional`, `gem_hrdps_continental`, `gem_hrdps_west`, `cmc_gem_gdps`, `cmc_gem_hrdps`, `cmc_gem_hrdps_west`, `cmc_gem_rdps` |
| **MetNo** | `metno_nordic`, `metno_seamless` |
| **CMA** | `cma_grapes_global` |
| **BOM** | `bom_access_global` |
| **UKMO** | `ukmo_seamless`, `ukmo_global_deterministic_10km`, `ukmo_uk_deterministic_2km` |
| **KMA** | `kma_seamless`, `kma_gdps`, `kma_ldps` |
| **KNMI/DMI** | `knmi_harmonie_arome_europe`, `knmi_harmonie_arome_netherlands`, `dmi_harmonie_arome_europe`, `knmi_seamless`, `dmi_seamless` |
| **MeteoSwiss** | `meteoswiss_icon_ch1`, `meteoswiss_icon_ch2`, `meteoswiss_icon_seamless` |
| **GeoSphere (Austria)** | `geosphere_arome_austria` |
| **Italia Meteo** | `italia_meteo_arpae_icon_2i` |
| **DWD SIS (satellite solar)** | `dwd_sis_europe_africa_v4` |

### Reanalysis / Archive Models

| Model | Description |
|-------|-------------|
| `archive_best_match` | Best reanalysis for location |
| `era5_seamless`, `era5`, `era5_land`, `era5_ensemble` | ECMWF ERA5 |
| `cerra` | EU CERRA reanalysis |
| `copernicus_era5_seamless`, `copernicus_era5`, `copernicus_cerra`, `copernicus_era5_land`, `copernicus_era5_ensemble` | Copernicus variants |
| `ecmwf_ifs_analysis`, `ecmwf_ifs_analysis_long_window` | ECMWF analysis |

### Satellite Radiation Models (Undocumented)

| Model | Coverage | Start |
|-------|----------|-------|
| `satellite_radiation_seamless` | Global | 1983 |
| `eumetsat_sarah3` | Europe/Africa | 1983 |
| `eumetsat_lsa_saf_msg` | Europe/Africa/Indian Ocean | recent |
| `eumetsat_lsa_saf_iodc` | Indian Ocean disk | recent |
| `jma_jaxa_himawari` | Asia/Pacific | recent |
| `jma_jaxa_mtg_fci` | Europe/Africa (new MTG satellite) | 2025+ |

### Ensemble Models

| Model | Members |
|-------|---------|
| `icon_seamless_eps`, `icon_global_eps`, `icon_eu_eps`, `icon_d2_eps` | 40 |
| `ecmwf_ifs025_ensemble` | 50 |
| `ecmwf_aifs025_ensemble` | 50 |
| `ncep_gefs_seamless`, `ncep_gefs025`, `ncep_gefs05` | 30 |
| `gem_global_ensemble` | 20 |
| `bom_access_global_ensemble` | 18 |
| `ukmo_global_ensemble_20km`, `ukmo_uk_ensemble_2km` | 18 |
| `meteoswiss_icon_ch1_ensemble`, `meteoswiss_icon_ch2_ensemble` | 11 |

Also available: ensemble mean variants (`*_ensemble_mean`) for all above.

### Seasonal Models

| Model | Months ahead | Members |
|-------|-------------|---------|
| `ecmwf_seasonal_seamless` | 7 months | 25 |
| `ecmwf_seas5` | 7 months | 25 |
| `ecmwf_ec46` | 7 months | 46 |

### Marine Models

| Model | Description |
|-------|-------------|
| `marine_best_match` | Best marine model |
| `ewam`, `gwam` | DWD wave models |
| `era5_ocean` | ERA5 ocean reanalysis |
| `ecmwf_wam025`, `ecmwf_wam025_ensemble` | ECMWF WAM wave model |
| `ncep_gfswave025`, `ncep_gfswave016` | GFS Wave |
| `ncep_gefswave025` | GEFS Wave ensemble |
| `meteofrance_wave`, `meteofrance_currents` | MeteoFrance wave & currents |

### Climate Projection Models (CMIP6)

| Model | Country | Resolution |
|-------|---------|------------|
| `MRI_AGCM3_2_S` | Japan | ~20 km |
| `EC_Earth3P_HR` | EU | ~25 km |
| `CMCC_CM2_VHR4` | Italy | ~25 km |
| `FGOALS_f3_H` | China | ~25 km |
| `HiRAM_SIT_HR` | Taiwan | ~25 km |
| `MPI_ESM1_2_XR` | Germany | ~50 km |
| `NICAM16_8S` | Japan | ~14 km |

### Flood Models

| Model | Description |
|-------|-------------|
| `flood_best_match` | Best flood model |
| `seamless_v4`, `forecast_v4`, `consolidated_v4` | GloFas v4 |
| `seamless_v3`, `forecast_v3`, `consolidated_v3` | GloFas v3 |

---

## Variable Catalogs

### Hourly Surface Variables (Forecast API)

**Temperature & Derived:**
`temperature_2m`, `apparent_temperature`, `wet_bulb_temperature_2m`, `dew_point_2m`, `relative_humidity_2m`, `vapour_pressure_deficit`

**Multi-level temperatures (height-based):**
`temperature_20m`, `temperature_40m`, `temperature_50m`, `temperature_80m`, `temperature_100m`, `temperature_120m`, `temperature_150m`, `temperature_180m`, `temperature_200m`

**Precipitation:**
`precipitation`, `rain`, `snowfall`, `showers`, `precipitation_probability`, `precipitation_type`, `snowfall_water_equivalent`, `hail`

**Wind:**
`wind_speed_10m`, `wind_direction_10m`, `wind_gusts_10m`
+ at heights: 20m, 30m, 40m, 50m, 70m, 80m, 100m, 120m, 140m, 150m, 160m, 180m, 200m, 250m, 300m, 350m, 450m

**Pressure & Atmosphere:**
`pressure_msl`, `surface_pressure`, `cloud_cover`, `cloud_cover_low`, `cloud_cover_mid`, `cloud_cover_high`, `cloud_cover_2m`, `cloud_base`, `cloud_top`, `convective_cloud_base`, `convective_cloud_top`, `cape`, `convective_inhibition`, `lifted_index`, `freezing_level_height`, `snowfall_height`, `boundary_layer_height`, `total_column_integrated_water_vapour`

**Solar Radiation:**
`shortwave_radiation`, `shortwave_radiation_instant`, `shortwave_radiation_clear_sky`, `direct_radiation`, `direct_radiation_instant`, `diffuse_radiation`, `diffuse_radiation_instant`, `direct_normal_irradiance`, `direct_normal_irradiance_instant`, `global_tilted_irradiance`, `global_tilted_irradiance_instant` (needs `tilt`/`azimuth`), `terrestrial_radiation`, `terrestrial_radiation_instant`, `sunshine_duration`

**Indices:**
`uv_index`, `uv_index_clear_sky`, `weather_code`, `visibility`, `is_day`

**Probabilities:**
`thunderstorm_probability`, `rain_probability`, `freezing_rain_probability`, `ice_pellets_probability`, `snowfall_probability`, `lightning_potential`, `leaf_wetness_probability`

**Soil:**
`soil_temperature_0cm`, `soil_temperature_6cm`, `soil_temperature_18cm`, `soil_temperature_54cm`
+ volumetric layers: 0-1cm, 1-3cm, 3-9cm, 9-27cm, 27-81cm, 0-7cm, 7-28cm, 28-100cm, 100-255cm, 0-10cm, 10-40cm, 40-100cm, 100-200cm
+ soil moisture index layers: 0-7cm, 7-28cm, 28-100cm, 100-255cm, 0-100cm

**Surface misc:**
`evapotranspiration`, `et0_fao_evapotranspiration`, `runoff`, `snow_depth`, `snow_depth_water_equivalent`, `surface_temperature`, `skin_temperature`, `sea_surface_temperature`, `latent_heat_flux`, `sensible_heat_flux`, `updraft`, `snow_density`, `mass_density_8m`, `albedo`, `k_index`, `roughness_length`, `growing_degree_days_base_0_limit_50`, `potential_evapotranspiration`

### Pressure-Level Variables (hPa)

Pattern: `{variable}_{level}hPa`

Variables: `temperature`, `relative_humidity`, `geopotential_height`, `wind_speed`, `wind_direction`, `vertical_velocity`, `cloud_cover`, `specific_humidity`

Levels: 30, 50, 70, 100, 150, 175, 200, 225, 250, 275, 300, 350, 400, 450, 500, 550, 600, 650, 700, 750, 800, 850, 900, 925, 950, 975, 1000 hPa

Example: `temperature_500hPa`, `wind_speed_850hPa`, `geopotential_height_500hPa`

### Ensemble Spread Variables (Undocumented)

Pattern: `{variable}_spread` - returns spread (standard deviation) across ensemble members.
Example: `temperature_2m_spread`, `wind_speed_10m_spread`, `precipitation_spread`

### Air Quality Variables

**Particulate matter:** `pm10`, `pm2_5`, `dust`, `pm10_wildfires`
**Gases:** `carbon_monoxide`, `nitrogen_dioxide`, `nitrogen_monoxide`, `sulphur_dioxide`, `ozone`, `ammonia`, `formaldehyde`, `glyoxal`, `non_methane_volatile_organic_compounds`, `peroxyacyl_nitrates`
**Greenhouse gases (undocumented):** `carbon_dioxide`, `methane`
**Aerosols:** `aerosol_optical_depth`, `secondary_inorganic_aerosol`, `residential_elementary_carbon`, `total_elementary_carbon`, `pm2_5_total_organic_matter`, `sea_salt_aerosol`
**AQI:** `european_aqi`, `us_aqi` + per-pollutant: `european_aqi_pm2_5`, `european_aqi_pm10`, `european_aqi_no2`, `european_aqi_o3`, `european_aqi_so2`, `us_aqi_pm2_5`, `us_aqi_pm10`, `us_aqi_no2`, `us_aqi_o3`, `us_aqi_so2`, `us_aqi_co`
**Pollen (Europe):** `alder_pollen`, `birch_pollen`, `grass_pollen`, `mugwort_pollen`, `olive_pollen`, `ragweed_pollen`
**UV:** `uv_index`, `uv_index_clear_sky`, `is_day`

### Marine Variables

Wave: `wave_height`, `wind_wave_height`, `swell_wave_height`, `wave_period`, `wind_wave_period`, `wind_wave_peak_period`, `swell_wave_period`, `swell_wave_peak_period`, `wave_direction`, `wind_wave_direction`, `swell_wave_direction`
Ocean: `ocean_current_velocity`, `ocean_current_direction`, `sea_surface_temperature`

### Flood Variables

`river_discharge`, `river_discharge_mean`, `river_discharge_min`, `river_discharge_max`, `river_discharge_median`, `river_discharge_p25`, `river_discharge_p75`

### Seasonal Weekly Variables (Undocumented)

Includes `_mean` and `_anomaly` pairs for: temperature_2m, dew_point_2m, precipitation, wind_speed_10m, wind_speed_100m, wind_gusts_10m, pressure_msl, cloud_cover, shortwave_radiation, longwave_radiation, sea_surface_temperature, snow_depth, snowfall, total_column_integrated_water_vapour.

Extreme indices: `temperature_2m_anomaly_gt0/gt1/gt2/ltm1/ltm2`, `temperature_2m_efi` (Extreme Forecast Index), `temperature_2m_sot10/sot90`, `precipitation_efi`, `precipitation_sot90`

---

## Output Formats

| Format | Description |
|--------|-------------|
| `json` | Default JSON response |
| `csv` | CSV with location header block |
| `xlsx` | Excel spreadsheet (filename from coordinates) |
| `flatbuffers` | Binary FlatBuffers format (most efficient for parsing at scale) |

---

## Advanced Features

### Batch Multi-Location Requests

Pass multiple lat/lon values as comma-separated strings or arrays. Returns a JSON array.

```
/v1/forecast?latitude=52.52,48.85,40.71&longitude=13.41,2.35,-74.01&...
```

### 15-Minute Resolution Data

Use `minutely_15` parameter instead of `hourly`. Supported by: GFS, ICON-D2, MeteoFrance AROME, Marine API.

```
/v1/forecast?latitude=52.52&longitude=13.41&minutely_15=temperature_2m,wind_speed_10m
```

### Bounding Box Queries

Retrieve data for all model grid points within a geographic box. Not supported for `best_match`; use specific models like `icon_eu`, `gfs025`, `ecmwf_ifs025`.

```
/v1/forecast?latitude=48.5&longitude=2.0&bounding_box=48.5,2.0,49.0,2.8&models=icon_eu&hourly=temperature_2m
```

### Solar Panel Optimization

For `global_tilted_irradiance` (GTI) and `global_tilted_irradiance_instant`:

```
/v1/forecast?...&hourly=global_tilted_irradiance&tilt=35&azimuth=0
```
- `tilt`: 0° = horizontal, 90° = vertical
- `azimuth`: 0° = south (optimal in N hemisphere), -90° = east, 90° = west

### Temporal Resolution Override

The `temporal_resolution` parameter forces a specific output dt regardless of native model resolution:
- `native`: model's native resolution
- `hourly` / `hourly_1`: 1-hour intervals
- `hourly_3`: 3-hour intervals
- `hourly_6`: 6-hour intervals

### Precise Time Ranges

For sub-day precision:
- `start_hour=2024-01-15T06:00&end_hour=2024-01-15T18:00` - specific hour window
- `past_hours=48&forecast_hours=24` - rolling window

### Single Model Run Queries (Undocumented)

Query the exact output from a specific model initialization time:

```
https://single-runs-api.open-meteo.com/v1/forecast?latitude=52.52&longitude=13.41
  &run=2024-01-15T00:00&hourly=temperature_2m&forecast_days=7
```

### Historical Forecast Archive (Semi-Undocumented)

Get the actual forecast output issued by models at past times (vs. ERA5 reanalysis):

```
https://historical-forecast-api.open-meteo.com/v1/forecast?latitude=52.52&longitude=13.41
  &start_date=2024-01-01&end_date=2024-01-31&hourly=temperature_2m&models=icon_global
```

### Greenhouse Gas Variables

`carbon_dioxide` (ppm) and `methane` (μg/m³) available via the air quality endpoint with `cams_global_greenhouse_gases` domain (accessible through the standard `cams_global` model).

---

## API Limits & Constraints

### Free Tier (api.open-meteo.com)
- Forecast: up to 16 forecast days, up to 93 past days
- Archive: 1940-01-01 to present
- Historical forecast: 2016-01-01 to present
- Air quality history: 2013-01-01 to present
- Flood history: 1984-01-01 to present
- Climate: 1950-2050

### Rate Limits
- No explicit rate limit on free tier (fair use)
- Large requests may return `HTTP 429` if too many variables requested simultaneously
- The `generationtime_ms` field in responses shows server processing time

### Commercial Tier
- Higher rate limits and SLA via `customer-*.open-meteo.com`
- Requires `&apikey=YOUR_KEY` parameter on all requests
- Same endpoints and parameters as free tier

---

## Python Client Usage

### Installation

No external dependencies required. Uses Python's built-in `urllib` and `json`.

```bash
# No pip install needed - copy open_meteo_client.py to your project
```

### Quick Start

```python
from open_meteo_client import OpenMeteoClient

client = OpenMeteoClient()

# Current + hourly + daily forecast
data = client.forecast(
    latitude=52.52,
    longitude=13.41,
    current=["temperature_2m", "wind_speed_10m", "weather_code"],
    hourly=["temperature_2m", "precipitation", "cloud_cover"],
    daily=["temperature_2m_max", "temperature_2m_min", "precipitation_sum"],
    forecast_days=7,
    timezone="Europe/Berlin",
)
print(f"Current temp: {data['current']['temperature_2m']}°C")
```

### Historical Data

```python
hist = client.historical(
    latitude=48.85, longitude=2.35,
    start_date="2023-01-01",
    end_date="2023-12-31",
    daily=["temperature_2m_max", "temperature_2m_min", "precipitation_sum"],
    timezone="Europe/Paris",
)
```

### Ensemble Forecasts

```python
ens = client.ensemble(
    latitude=52.52, longitude=13.41,
    hourly=["temperature_2m"],
    models=["ecmwf_ifs025_ensemble"],
    forecast_days=14,
)
# Returns temperature_2m, temperature_2m_member01 ... temperature_2m_member50
```

### Air Quality with Greenhouse Gases

```python
aq = client.air_quality(
    latitude=52.52, longitude=13.41,
    current=["pm10", "pm2_5", "european_aqi"],
    hourly=["carbon_dioxide", "methane", "ozone", "european_aqi"],
    forecast_days=3,
)
```

### Marine Weather

```python
marine = client.marine(
    latitude=51.5, longitude=1.5,
    hourly=["wave_height", "swell_wave_height", "wave_period", "wave_direction"],
    daily=["wave_height_max", "wave_direction_dominant"],
    forecast_days=7,
)
```

### Climate Projections

```python
climate = client.climate(
    latitude=52.52, longitude=13.41,
    start_date="2040-01-01", end_date="2040-12-31",
    daily=["temperature_2m_max", "temperature_2m_min", "precipitation_sum"],
    models=["MRI_AGCM3_2_S"],
)
```

### Batch Multi-Location

```python
cities_lat = [52.52, 48.85, 40.71, 35.69, 55.75]
cities_lon = [13.41, 2.35, -74.01, 139.69, 37.62]

batch = client.forecast(
    latitude=cities_lat,
    longitude=cities_lon,
    current=["temperature_2m"],
    forecast_days=1,
)
# Returns list of dicts, one per location
for loc in batch:
    print(f"{loc['latitude']:.2f}°N, {loc['longitude']:.2f}°E: {loc['current']['temperature_2m']}°C")
```

### Pressure Level Data

```python
upper_air = client.forecast(
    latitude=52.52, longitude=13.41,
    hourly=[
        "temperature_500hPa", "temperature_850hPa",
        "geopotential_height_500hPa",
        "wind_speed_850hPa", "wind_direction_850hPa",
        "relative_humidity_700hPa",
    ],
    forecast_days=3,
)
```

### Solar Panel Optimization

```python
solar = client.forecast(
    latitude=48.85, longitude=2.35,
    hourly=["global_tilted_irradiance", "direct_normal_irradiance"],
    tilt=35,      # panel tilt in degrees
    azimuth=0,    # 0=south-facing
    forecast_days=7,
)
```

### Undocumented: Single Model Run

```python
# Get the exact forecast issued at a specific model initialization time
run = client.single_run(
    latitude=52.52, longitude=13.41,
    run="2026-03-24T00:00",
    hourly=["temperature_2m", "precipitation"],
    forecast_days=3,
)
```

### Undocumented: Satellite Radiation Data

```python
# Historical solar radiation from satellites (back to 1983)
sat = client.satellite_radiation(
    latitude=48.85, longitude=2.35,
    start_date="2024-06-01", end_date="2024-06-30",
    hourly=["shortwave_radiation", "direct_radiation", "sunshine_duration"],
    models=["satellite_radiation_seamless"],
)
```

### Geocoding

```python
# Search by name
results = client.geocode("Tokyo", count=5, language="en")
location = results["results"][0]

# Get by GeoNames ID (undocumented endpoint)
berlin = client.geocode_by_id(2950159)
```

### Commercial API (with API key)

```python
client = OpenMeteoClient(api_key="YOUR_API_KEY")
# All methods work the same, automatically routed to customer-*.open-meteo.com
data = client.forecast(latitude=52.52, longitude=13.41, hourly=["temperature_2m"])
```

---

## Response Structure

All JSON responses include:

```json
{
    "latitude": 52.52,
    "longitude": 13.42,
    "generationtime_ms": 0.45,
    "utc_offset_seconds": 0,
    "timezone": "GMT",
    "timezone_abbreviation": "GMT",
    "elevation": 38.0,
    "current_units": {"time": "iso8601", "temperature_2m": "°C", ...},
    "current": {"time": "2026-03-25T02:00", "temperature_2m": 10.5, ...},
    "hourly_units": {"time": "iso8601", "temperature_2m": "°C", ...},
    "hourly": {"time": [...], "temperature_2m": [...], ...},
    "daily_units": {"time": "iso8601", "temperature_2m_max": "°C", ...},
    "daily": {"time": [...], "temperature_2m_max": [...], ...}
}
```

Batch requests return a JSON array `[{...}, {...}, ...]`.

---

## Key Findings Summary

1. **13 distinct API subdomains** including 4 that are minimally or not documented
2. **~200+ models** across forecast, reanalysis, ensemble, seasonal, marine, climate, flood categories
3. **~300+ hourly variables** including all pressure levels, height-based winds, soil profiles
4. **Greenhouse gases** (CO2, CH4) accessible via air quality API but not prominently documented
5. **Pollen forecasts** (6 species) available for Europe via CAMS model
6. **15-minute resolution** data available for GFS, ICON-D2, MeteoFrance AROME models
7. **Binary FlatBuffers** output format available for efficient large-scale data processing
8. **Excel (XLSX)** output available for direct spreadsheet download
9. **Bounding box queries** return all grid points within a geographic box
10. **Solar panel optimization** via `tilt` + `azimuth` parameters for GTI calculation
11. **Single-run API** allows querying exact model initialization outputs (undocumented)
12. **Satellite radiation** archive back to 1983 via `satellite-api.open-meteo.com` (undocumented)
13. **Ensemble spread variables** available as `{var}_spread` pattern
14. **Seasonal anomaly/EFI variables** for probabilistic climate outlooks
15. **All APIs support POST** in addition to GET with identical parameters (via JSON body)
