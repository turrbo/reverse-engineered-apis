#!/usr/bin/env python3
"""
Open-Meteo Comprehensive API Client
=====================================
Reverse-engineered from open-meteo.com including both documented and
undocumented/internal endpoints discovered via source code analysis.

Source: https://github.com/open-meteo/open-meteo
Reverse-engineered: 2026-03-25

APIs Covered:
  - Weather Forecast (api.open-meteo.com) - all models
  - Historical Weather Archive (archive-api.open-meteo.com)
  - Historical Forecast (historical-forecast-api.open-meteo.com)  [semi-undocumented]
  - Previous Model Runs (previous-runs-api.open-meteo.com)        [semi-undocumented]
  - Single Model Runs (single-runs-api.open-meteo.com)            [undocumented]
  - Marine Weather (marine-api.open-meteo.com)
  - Air Quality (air-quality-api.open-meteo.com) incl. greenhouse gases
  - Ensemble Forecasts (ensemble-api.open-meteo.com)
  - Seasonal Forecasts (seasonal-api.open-meteo.com)
  - Climate Projections (climate-api.open-meteo.com)
  - Flood / GloFas (flood-api.open-meteo.com)
  - Elevation / DEM (api.open-meteo.com/v1/elevation)
  - Geocoding (geocoding-api.open-meteo.com)
  - Satellite Radiation (satellite-api.open-meteo.com)            [undocumented]
  - Commercial/Customer APIs (customer-*.open-meteo.com)          [requires API key]

Key Undocumented Features Discovered:
  - single-runs-api: query specific model run times
  - satellite-api: satellite-derived radiation data back to 1983
  - historical-forecast-api: archived forecasts back to 2016
  - previous-runs-api: compare current vs previous model runs
  - bounding_box: spatial queries over a geographic box
  - minutely_15: 15-minute resolution data
  - weekly/monthly: aggregated weekly/monthly data
  - temporal_resolution: override output resolution (native/hourly/hourly_3/hourly_6)
  - tilt/azimuth: solar panel orientation for GTI calculation
  - format=flatbuffers: binary FlatBuffers format for efficiency
  - format=xlsx: Excel spreadsheet output
  - location_information=omit: omit location metadata from output
  - initial_hours/initial_minutely_15: hour offset for forecast_hours
  - start_hour/end_hour: precise hourly time range selection
  - cell_selection=sea/land/nearest: grid cell selection mode
  - disable_bias_correction: skip bias correction in climate API
  - ensemble=true: enable ensemble members for flood river_discharge
  - multiple latitudes/longitudes: batch multi-location requests
  - pressure-level variables: temperature_850hPa, wind_speed_500hPa, etc.
  - spread variables: temperature_2m_spread (ensemble spread)
  - anomaly variables: temperature_2m_anomaly (seasonal)
  - greenhouse gases: carbon_dioxide, methane via air-quality API
  - pollen variables: alder_pollen, birch_pollen, grass_pollen, etc.
  - AQI indices: european_aqi, us_aqi and per-pollutant sub-indices
"""

import urllib.request
import urllib.parse
import json
import time
from typing import Optional, Union, List, Dict, Any


# ---------------------------------------------------------------------------
# Constants - all known API base URLs
# ---------------------------------------------------------------------------

BASE_URLS = {
    "forecast":             "https://api.open-meteo.com/v1/forecast",
    "archive":              "https://archive-api.open-meteo.com/v1/archive",
    "era5":                 "https://archive-api.open-meteo.com/v1/era5",
    "historical_forecast":  "https://historical-forecast-api.open-meteo.com/v1/forecast",
    "previous_runs":        "https://previous-runs-api.open-meteo.com/v1/forecast",
    "single_runs":          "https://single-runs-api.open-meteo.com/v1/forecast",
    "satellite":            "https://satellite-api.open-meteo.com/v1/archive",
    "ensemble":             "https://ensemble-api.open-meteo.com/v1/ensemble",
    "seasonal":             "https://seasonal-api.open-meteo.com/v1/seasonal",
    "marine":               "https://marine-api.open-meteo.com/v1/marine",
    "air_quality":          "https://air-quality-api.open-meteo.com/v1/air-quality",
    "climate":              "https://climate-api.open-meteo.com/v1/climate",
    "flood":                "https://flood-api.open-meteo.com/v1/flood",
    "elevation":            "https://api.open-meteo.com/v1/elevation",
    "geocoding":            "https://geocoding-api.open-meteo.com/v1/search",
    "geocoding_get":        "https://geocoding-api.open-meteo.com/v1/get",
    # model-specific shortcuts
    "dwd_icon":             "https://api.open-meteo.com/v1/dwd-icon",
    "gfs":                  "https://api.open-meteo.com/v1/gfs",
    "ecmwf":                "https://api.open-meteo.com/v1/ecmwf",
    "meteofrance":          "https://api.open-meteo.com/v1/meteofrance",
    "jma":                  "https://api.open-meteo.com/v1/jma",
    "metno":                "https://api.open-meteo.com/v1/metno",
    "gem":                  "https://api.open-meteo.com/v1/gem",
    "cma":                  "https://api.open-meteo.com/v1/cma",
    "bom":                  "https://api.open-meteo.com/v1/bom",
    # commercial (requires &apikey=)
    "customer_forecast":    "https://customer-api.open-meteo.com/v1/forecast",
    "customer_archive":     "https://customer-archive-api.open-meteo.com/v1/archive",
    "customer_ensemble":    "https://customer-ensemble-api.open-meteo.com/v1/ensemble",
    "customer_seasonal":    "https://customer-seasonal-api.open-meteo.com/v1/seasonal",
    "customer_marine":      "https://customer-marine-api.open-meteo.com/v1/marine",
    "customer_air_quality": "https://customer-air-quality-api.open-meteo.com/v1/air-quality",
    "customer_climate":     "https://customer-climate-api.open-meteo.com/v1/climate",
    "customer_flood":       "https://customer-flood-api.open-meteo.com/v1/flood",
    "customer_hist_forecast": "https://customer-historical-forecast-api.open-meteo.com/v1/forecast",
    "customer_prev_runs":   "https://customer-previous-runs-api.open-meteo.com/v1/forecast",
    "customer_single_runs": "https://customer-single-runs-api.open-meteo.com/v1/forecast",
    "customer_satellite":   "https://customer-satellite-api.open-meteo.com/v1/archive",
}

# ---------------------------------------------------------------------------
# All known forecast models (from ForecastapiController.swift)
# ---------------------------------------------------------------------------

FORECAST_MODELS = {
    # Best match / automatic selection
    "best_match",

    # NCEP / GFS models
    "gfs_seamless", "gfs_global", "gfs025", "gfs05", "gfs013",
    "gfs_hrrr", "gfs_graphcast025",
    "ncep_seamless", "ncep_gfs_global", "ncep_nbm_conus",
    "ncep_gfs025", "ncep_gfs013", "ncep_hrrr_conus", "ncep_hrrr_conus_15min",
    "ncep_gfs_graphcast025", "ncep_nam_conus",
    "ncep_aigfs025",       # AI-GFS (experimental)
    "ncep_aigefs025",      # AI-GEFS (experimental)
    "ncep_hgefs025_ensemble_mean",
    "ncep_aigefs025_ensemble_mean",

    # MeteoFrance / AROME / ARPEGE
    "meteofrance_seamless", "meteofrance_arpege_seamless", "meteofrance_arpege_world",
    "meteofrance_arpege_europe", "meteofrance_arome_seamless", "meteofrance_arome_france",
    "meteofrance_arome_france0025", "meteofrance_arpege_world025",
    "meteofrance_arome_france_hd", "meteofrance_arome_france_hd_15min",
    "meteofrance_arome_france_15min",
    # legacy aliases
    "arpege_seamless", "arpege_world", "arpege_europe",
    "arome_seamless", "arome_france", "arome_france_hd",

    # JMA (Japan)
    "jma_seamless", "jma_msm", "jma_gsm",

    # GEM / CMC (Canada)
    "gem_seamless", "gem_global", "gem_regional", "gem_hrdps_continental", "gem_hrdps_west",
    "cmc_gem_gdps", "cmc_gem_hrdps", "cmc_gem_hrdps_west", "cmc_gem_rdps",

    # DWD ICON (Germany)
    "icon_seamless", "icon_global", "icon_eu", "icon_d2",
    "dwd_icon_seamless", "dwd_icon_global", "dwd_icon", "dwd_icon_eu",
    "dwd_icon_d2", "dwd_icon_d2_15min",
    "dwd_sis_europe_africa_v4",  # satellite-based solar irradiance

    # ECMWF
    "ecmwf_ifs04", "ecmwf_ifs025",
    "ecmwf_aifs025",         # AI-based AIFS single
    "ecmwf_aifs025_single",
    "ecmwf_ifs", "ecmwf_ifs_analysis", "ecmwf_ifs_analysis_long_window",
    "ecmwf_ifs_long_window", "ecmwf_wam",

    # MetNo (Norway)
    "metno_nordic", "metno_seamless",

    # GeoSphere Austria
    "geosphere_arome_austria",

    # CMA (China)
    "cma_grapes_global",

    # BOM (Australia)
    "bom_access_global",

    # ARPAE (Italy)
    "arpae_cosmo_seamless", "arpae_cosmo_2i", "arpae_cosmo_2i_ruc", "arpae_cosmo_5m",

    # KNMI / DMI (Netherlands / Denmark)
    "knmi_harmonie_arome_europe", "knmi_harmonie_arome_netherlands",
    "dmi_harmonie_arome_europe",
    "knmi_seamless", "dmi_seamless",

    # UKMO (UK Met Office)
    "ukmo_seamless", "ukmo_global_deterministic_10km", "ukmo_uk_deterministic_2km",

    # KMA (South Korea)
    "kma_seamless", "kma_gdps", "kma_ldps",

    # Italia Meteo
    "italia_meteo_arpae_icon_2i",

    # MeteoSwiss
    "meteoswiss_icon_ch1", "meteoswiss_icon_ch2", "meteoswiss_icon_seamless",

    # ERA5 / Reanalysis
    "archive_best_match", "era5_seamless", "era5", "cerra", "era5_land", "era5_ensemble",
    "copernicus_era5_seamless", "copernicus_era5", "copernicus_cerra",
    "copernicus_era5_land", "copernicus_era5_ensemble",

    # Satellite radiation
    "satellite_radiation_seamless",
    "eumetsat_sarah3",
    "eumetsat_lsa_saf_msg", "eumetsat_lsa_saf_iodc",
    "jma_jaxa_himawari", "jma_jaxa_mtg_fci",
}

ENSEMBLE_MODELS = {
    "icon_seamless_eps", "icon_global_eps", "icon_eu_eps", "icon_d2_eps",
    "ecmwf_ifs025_ensemble", "ecmwf_aifs025_ensemble",
    "gem_global_ensemble",
    "bom_access_global_ensemble",
    "ncep_gefs_seamless", "ncep_gefs025", "ncep_gefs05",
    "ukmo_global_ensemble_20km", "ukmo_uk_ensemble_2km",
    "meteoswiss_icon_ch1_ensemble", "meteoswiss_icon_ch2_ensemble",
    # Ensemble means
    "dwd_icon_eps_ensemble_mean_seamless", "dwd_icon_eps_ensemble_mean",
    "dwd_icon_eu_eps_ensemble_mean", "dwd_icon_d2_eps_ensemble_mean",
    "ecmwf_ifs025_ensemble_mean", "ecmwf_aifs025_ensemble_mean",
    "ncep_gefs025_ensemble_mean", "ncep_gefs05_ensemble_mean",
    "ncep_gefs_ensemble_mean_seamless",
    "cmc_gem_geps_ensemble_mean",
    "bom_access_global_ensemble_mean",
    "ukmo_global_ensemble_mean_20km", "ukmo_uk_ensemble_mean_2km",
    "meteoswiss_icon_ch1_ensemble_mean", "meteoswiss_icon_ch2_ensemble_mean",
}

SEASONAL_MODELS = {
    "ecmwf_seasonal_seamless", "ecmwf_seas5", "ecmwf_ec46",
    "ecmwf_seasonal_ensemble_mean_seamless",
    "ecmwf_seas5_ensemble_mean", "ecmwf_ec46_ensemble_mean",
}

MARINE_MODELS = {
    "marine_best_match",
    "ewam", "gwam", "era5_ocean",
    "ecmwf_wam025", "ecmwf_wam025_ensemble", "ecmwf_wam025_ensemble_mean",
    "ncep_gfswave025", "ncep_gfswave016",
    "ncep_gefswave025", "ncep_gefswave025_ensemble_mean",
    "meteofrance_wave", "meteofrance_currents",
}

AIR_QUALITY_MODELS = {
    "air_quality_best_match", "cams_global", "cams_europe",
}

CLIMATE_MODELS = {
    "CMCC_CM2_VHR4", "FGOALS_f3_H", "HiRAM_SIT_HR",
    "MRI_AGCM3_2_S", "EC_Earth3P_HR", "MPI_ESM1_2_XR", "NICAM16_8S",
}

FLOOD_MODELS = {
    "flood_best_match",
    "seamless_v3", "forecast_v3", "consolidated_v3",
    "seamless_v4", "forecast_v4", "consolidated_v4",
}

# ---------------------------------------------------------------------------
# Weather variable catalogs
# ---------------------------------------------------------------------------

HOURLY_VARIABLES = [
    # Temperature
    "temperature_2m", "temperature_20m", "temperature_40m", "temperature_50m",
    "temperature_80m", "temperature_100m", "temperature_120m", "temperature_150m",
    "temperature_180m", "temperature_200m",
    # Apparent / Wet bulb
    "apparent_temperature", "wet_bulb_temperature_2m",
    # Humidity / Dew point
    "relative_humidity_2m", "dew_point_2m", "vapour_pressure_deficit",
    # Precipitation
    "precipitation", "rain", "snowfall", "showers",
    "precipitation_probability",
    # Cloud / radiation
    "cloud_cover", "cloud_cover_low", "cloud_cover_mid", "cloud_cover_high",
    "cloud_cover_2m", "cloud_base", "cloud_top",
    "convective_cloud_base", "convective_cloud_top",
    "shortwave_radiation", "shortwave_radiation_instant",
    "shortwave_radiation_clear_sky", "shortwave_radiation_clear_sky_instant",
    "direct_radiation", "direct_radiation_instant",
    "diffuse_radiation", "diffuse_radiation_instant",
    "direct_normal_irradiance", "direct_normal_irradiance_instant",
    "global_tilted_irradiance", "global_tilted_irradiance_instant",
    "terrestrial_radiation", "terrestrial_radiation_instant",
    "sunshine_duration",
    # Wind
    "wind_speed_10m", "wind_direction_10m", "wind_gusts_10m",
    "wind_speed_20m", "wind_direction_20m",
    "wind_speed_30m", "wind_direction_30m",
    "wind_speed_40m", "wind_direction_40m",
    "wind_speed_50m", "wind_direction_50m",
    "wind_speed_70m", "wind_direction_70m",
    "wind_speed_80m", "wind_direction_80m",
    "wind_speed_100m", "wind_direction_100m",
    "wind_speed_120m", "wind_direction_120m",
    "wind_speed_140m", "wind_direction_140m",
    "wind_speed_150m", "wind_direction_150m",
    "wind_speed_160m", "wind_direction_160m",
    "wind_speed_180m", "wind_direction_180m",
    "wind_speed_200m", "wind_direction_200m",
    "wind_speed_250m", "wind_direction_250m",
    "wind_speed_300m", "wind_direction_300m",
    "wind_speed_350m", "wind_direction_350m",
    "wind_speed_450m", "wind_direction_450m",
    # Pressure
    "pressure_msl", "surface_pressure",
    # Misc surface
    "weather_code", "visibility",
    "cape", "convective_inhibition", "lifted_index",
    "freezing_level_height", "snowfall_height",
    "uv_index", "uv_index_clear_sky",
    "is_day",
    "surface_temperature", "skin_temperature",
    "evapotranspiration", "et0_fao_evapotranspiration",
    "runoff",
    "snow_depth", "snow_depth_water_equivalent",
    "total_column_integrated_water_vapour",
    "boundary_layer_height",
    "growing_degree_days_base_0_limit_50",
    "leaf_wetness_probability",
    "lightning_potential",
    "thunderstorm_probability",
    "rain_probability", "freezing_rain_probability",
    "ice_pellets_probability", "snowfall_probability",
    "albedo", "k_index", "roughness_length",
    "potential_evapotranspiration",
    "latent_heat_flux", "sensible_heat_flux",
    "updraft", "hail", "snow_density",
    "mass_density_8m",
    "precipitation_type",
    # Soil temperature
    "soil_temperature_0cm", "soil_temperature_6cm", "soil_temperature_18cm",
    "soil_temperature_54cm",
    "soil_temperature_0_to_7cm", "soil_temperature_7_to_28cm",
    "soil_temperature_28_to_100cm", "soil_temperature_100_to_255cm",
    "soil_temperature_0_to_10cm", "soil_temperature_10_to_40cm",
    "soil_temperature_40_to_100cm", "soil_temperature_100_to_200cm",
    "soil_temperature_0_to_100cm",
    # Soil moisture
    "soil_moisture_0_to_1cm", "soil_moisture_1_to_3cm", "soil_moisture_3_to_9cm",
    "soil_moisture_9_to_27cm", "soil_moisture_27_to_81cm",
    "soil_moisture_0_to_7cm", "soil_moisture_7_to_28cm",
    "soil_moisture_28_to_100cm", "soil_moisture_100_to_255cm",
    "soil_moisture_0_to_10cm", "soil_moisture_10_to_40cm",
    "soil_moisture_40_to_100cm", "soil_moisture_100_to_200cm",
    "soil_moisture_0_to_100cm",
    "soil_moisture_index_0_to_7cm", "soil_moisture_index_7_to_28cm",
    "soil_moisture_index_28_to_100cm", "soil_moisture_index_100_to_255cm",
    "soil_moisture_index_0_to_100cm",
    # Sea surface
    "sea_surface_temperature",
]

# Pressure-level variables pattern: {var}_{level}hPa
PRESSURE_LEVEL_VARIABLES = [
    "temperature", "relative_humidity", "geopotential_height",
    "wind_speed", "wind_direction",
    "vertical_velocity", "cloud_cover",
    "specific_humidity",
]
PRESSURE_LEVELS = [
    30, 50, 70, 100, 150, 175, 200, 225, 250, 275, 300, 350,
    400, 450, 500, 550, 600, 650, 700, 750, 800, 850, 900,
    925, 950, 975, 1000,
]

DAILY_VARIABLES = [
    "temperature_2m_max", "temperature_2m_min", "temperature_2m_mean",
    "apparent_temperature_max", "apparent_temperature_min", "apparent_temperature_mean",
    "precipitation_sum", "rain_sum", "snowfall_sum", "showers_sum",
    "precipitation_hours",
    "precipitation_probability_max", "precipitation_probability_min",
    "precipitation_probability_mean",
    "weather_code",
    "sunrise", "sunset", "daylight_duration", "sunshine_duration",
    "wind_speed_10m_max", "wind_speed_10m_min", "wind_speed_10m_mean",
    "wind_gusts_10m_max", "wind_gusts_10m_min", "wind_gusts_10m_mean",
    "wind_direction_10m_dominant",
    "wind_speed_100m_max", "wind_speed_100m_min", "wind_speed_100m_mean",
    "wind_direction_100m_dominant",
    "wind_speed_200m_max", "wind_speed_200m_min", "wind_speed_200m_mean",
    "wind_direction_200m_dominant",
    "shortwave_radiation_sum",
    "et0_fao_evapotranspiration",
    "uv_index_max", "uv_index_clear_sky_max",
    "visibility_max", "visibility_min", "visibility_mean",
    "pressure_msl_max", "pressure_msl_min", "pressure_msl_mean",
    "surface_pressure_max", "surface_pressure_min", "surface_pressure_mean",
    "cloud_cover_max", "cloud_cover_min", "cloud_cover_mean",
    "dew_point_2m_max", "dew_point_2m_min", "dew_point_2m_mean",
    "relative_humidity_2m_max", "relative_humidity_2m_min", "relative_humidity_2m_mean",
    "wet_bulb_temperature_2m_max", "wet_bulb_temperature_2m_min",
    "wet_bulb_temperature_2m_mean",
    "vapor_pressure_deficit_max",
    "growing_degree_days_base_0_limit_50",
    "leaf_wetness_probability_mean",
    "soil_moisture_0_to_100cm_mean", "soil_moisture_0_to_10cm_mean",
    "soil_moisture_0_to_7cm_mean", "soil_moisture_7_to_28cm_mean",
    "soil_moisture_28_to_100cm_mean", "soil_moisture_100_to_255cm_mean",
    "soil_moisture_index_0_to_7cm_mean", "soil_moisture_index_7_to_28cm_mean",
    "soil_moisture_index_28_to_100cm_mean", "soil_moisture_index_100_to_255cm_mean",
    "soil_moisture_index_0_to_100cm_mean",
    "soil_temperature_0_to_7cm_mean", "soil_temperature_7_to_28cm_mean",
    "soil_temperature_28_to_100cm_mean", "soil_temperature_100_to_255cm_mean",
    "soil_temperature_0_to_100cm_mean", "soil_temperature_0_to_10cm_mean",
    "snow_depth_min", "snow_depth_mean", "snow_depth_max",
    "snowfall_water_equivalent_sum",
    "cape_max", "cape_mean", "cape_min",
    "updraft_max",
    "wave_height_max", "wind_wave_height_max", "swell_wave_height_max",
    "wave_direction_dominant", "wind_wave_direction_dominant", "swell_wave_direction_dominant",
    "wave_period_max", "wind_wave_period_max", "swell_wave_period_max",
    "wind_wave_peak_period_max", "swell_wave_peak_period_max",
    "sea_surface_temperature_min", "sea_surface_temperature_max",
    "sea_surface_temperature_mean",
    "river_discharge", "river_discharge_mean", "river_discharge_min",
    "river_discharge_max", "river_discharge_median",
    "river_discharge_p25", "river_discharge_p75",
]

MARINE_VARIABLES = [
    # Wave height
    "wave_height", "wind_wave_height", "swell_wave_height",
    # Wave period
    "wave_period", "wind_wave_period", "wind_wave_peak_period",
    "swell_wave_period", "swell_wave_peak_period",
    # Wave direction
    "wave_direction", "wind_wave_direction", "swell_wave_direction",
    # Ocean surface
    "ocean_current_velocity", "ocean_current_direction",
    "sea_surface_temperature",
]

AIR_QUALITY_VARIABLES = [
    # Particulate matter
    "pm10", "pm2_5", "dust",
    "pm10_wildfires",
    # Gases
    "carbon_monoxide", "nitrogen_dioxide", "sulphur_dioxide",
    "ozone", "ammonia", "nitrogen_monoxide",
    "formaldehyde", "glyoxal",
    "non_methane_volatile_organic_compounds",
    "peroxyacyl_nitrates",
    # Greenhouse gases (undocumented for most users)
    "carbon_dioxide", "methane",
    # AQI indices
    "european_aqi", "european_aqi_pm2_5", "european_aqi_pm10",
    "european_aqi_no2", "european_aqi_o3", "european_aqi_so2",
    "us_aqi", "us_aqi_pm2_5", "us_aqi_pm10",
    "us_aqi_no2", "us_aqi_o3", "us_aqi_so2", "us_aqi_co",
    # Aerosols
    "aerosol_optical_depth",
    "secondary_inorganic_aerosol", "residential_elementary_carbon",
    "total_elementary_carbon", "pm2_5_total_organic_matter",
    "sea_salt_aerosol",
    # Pollen (Europe only via CAMS)
    "alder_pollen", "birch_pollen", "grass_pollen",
    "mugwort_pollen", "olive_pollen", "ragweed_pollen",
    # UV
    "uv_index", "uv_index_clear_sky",
    # Misc
    "is_day",
]

CLIMATE_VARIABLES = [
    "temperature_2m_max", "temperature_2m_min", "temperature_2m_mean",
    "precipitation_sum", "rain_sum", "snowfall_sum",
    "shortwave_radiation_sum",
    "wind_speed_10m_max", "wind_speed_10m_mean",
    "wind_gusts_10m_mean", "wind_gusts_10m_max",
    "wind_direction_10m_dominant",
    "et0_fao_evapotranspiration_sum",
    "cloud_cover_mean",
    "soil_moisture_0_to_10cm_mean", "soil_moisture_0_to_100cm_mean",
    "soil_temperature_0_to_7cm_mean",
    "relative_humidity_2m_max", "relative_humidity_2m_min",
    "dew_point_2m_max", "dew_point_2m_min", "dew_point_2m_mean",
    "vapour_pressure_deficit_max",
    "vapor_pressure_deficit_max",
    "growing_degree_days_base_0_limit_50",
    "soil_moisture_index_0_to_10cm_mean", "soil_moisture_index_0_to_100cm_mean",
    "soil_moisture_0_to_7cm_mean", "soil_moisture_7_to_28cm_mean",
    "soil_moisture_28_to_100cm_mean",
    "daylight_duration",
    "leaf_wetness_probability_mean",
    "sunshine_duration",
]

FLOOD_VARIABLES = [
    "river_discharge",
    "river_discharge_mean", "river_discharge_min", "river_discharge_max",
    "river_discharge_median", "river_discharge_p25", "river_discharge_p75",
]

# Seasonal weekly/monthly variables
SEASONAL_WEEKLY_VARIABLES = [
    "temperature_2m_mean", "temperature_2m_anomaly",
    "dew_point_2m_mean", "dew_point_2m_anomaly",
    "precipitation_mean", "precipitation_anomaly",
    "precipitation_anomaly_gt0", "precipitation_anomaly_gt10", "precipitation_anomaly_gt20",
    "wind_speed_10m_mean", "wind_speed_10m_anomaly",
    "wind_direction_10m_mean", "wind_direction_10m_anomaly",
    "wind_speed_100m_mean", "wind_speed_100m_anomaly",
    "wind_direction_100m_mean", "wind_direction_100m_anomaly",
    "wind_gusts_10m_mean", "wind_gusts_10m_anomaly",
    "pressure_msl_mean", "pressure_msl_anomaly",
    "cloud_cover_mean", "cloud_cover_anomaly",
    "shortwave_radiation_mean", "shortwave_radiation_anomaly",
    "sea_surface_temperature_mean", "sea_surface_temperature_anomaly",
    "snow_depth_mean", "snow_depth_anomaly",
    "snowfall_mean", "snowfall_anomaly",
    "total_column_integrated_water_vapour_mean",
    "temperature_2m_anomaly_gt0", "temperature_2m_anomaly_gt1", "temperature_2m_anomaly_gt2",
    "temperature_2m_anomaly_ltm1", "temperature_2m_anomaly_ltm2",
    "temperature_2m_efi", "precipitation_efi",
    "temperature_2m_sot10", "temperature_2m_sot90",
    "precipitation_sot90",
]

SEASONAL_MONTHLY_VARIABLES = [
    "temperature_2m_mean", "temperature_2m_anomaly",
    "dew_point_2m_mean", "dew_point_2m_anomaly",
    "precipitation_mean", "precipitation_anomaly",
    "wind_speed_10m_mean", "wind_speed_10m_anomaly",
    "pressure_msl_mean", "pressure_msl_anomaly",
    "cloud_cover_mean", "cloud_cover_anomaly",
    "shortwave_radiation_mean", "shortwave_radiation_anomaly",
    "longwave_radiation_mean", "longwave_radiation_anomaly",
    "sea_surface_temperature_mean", "sea_surface_temperature_anomaly",
    "snow_depth_mean", "snow_depth_anomaly",
    "snowfall_water_equivalent_mean", "snowfall_water_equivalent_anomaly",
    "precipitation_anomaly_gt0", "precipitation_anomaly_gt10", "precipitation_anomaly_gt20",
    "soil_temperature_0_to_7cm_mean",
    "soil_moisture_0_to_7cm_mean",
]

# ---------------------------------------------------------------------------
# Core HTTP helper
# ---------------------------------------------------------------------------

def _get(url: str, params: dict, timeout: int = 30) -> dict:
    """Make a GET request and return parsed JSON."""
    # Build query string - handle list values with comma-separation
    parts = []
    for k, v in params.items():
        if v is None:
            continue
        if isinstance(v, (list, tuple)):
            if len(v) == 0:
                continue
            parts.append(f"{k}={','.join(str(x) for x in v)}")
        elif isinstance(v, bool):
            parts.append(f"{k}={'true' if v else 'false'}")
        else:
            parts.append(f"{k}={urllib.parse.quote(str(v), safe=',')}")
    full_url = f"{url}?{'&'.join(parts)}" if parts else url
    req = urllib.request.Request(full_url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _post(url: str, payload: dict, timeout: int = 30) -> dict:
    """Make a POST request with JSON body and return parsed JSON."""
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url, data=data,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST"
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


# ---------------------------------------------------------------------------
# Main Client Class
# ---------------------------------------------------------------------------

class OpenMeteoClient:
    """
    Comprehensive Open-Meteo API client covering all known endpoints.

    Usage:
        client = OpenMeteoClient()                        # free tier
        client = OpenMeteoClient(api_key="your_key")     # commercial tier

    All methods accept both single values and lists for lat/lon (batch).
    """

    def __init__(self, api_key: Optional[str] = None, timeout: int = 30):
        self.api_key = api_key
        self.timeout = timeout
        self._base = "customer" if api_key else ""

    def _url(self, name: str) -> str:
        key = f"customer_{name}" if self.api_key else name
        return BASE_URLS.get(key, BASE_URLS.get(name, ""))

    def _common(self, extra: dict) -> dict:
        p = {}
        if self.api_key:
            p["apikey"] = self.api_key
        p.update({k: v for k, v in extra.items() if v is not None})
        return p

    # -----------------------------------------------------------------------
    # Weather Forecast API
    # -----------------------------------------------------------------------

    def forecast(
        self,
        latitude: Union[float, List[float]],
        longitude: Union[float, List[float]],
        # Time range (use one of these approaches)
        forecast_days: int = 7,
        past_days: int = 0,
        past_hours: Optional[int] = None,
        forecast_hours: Optional[int] = None,
        initial_hours: Optional[int] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        start_hour: Optional[str] = None,
        end_hour: Optional[str] = None,
        # Variables
        current: Optional[List[str]] = None,
        hourly: Optional[List[str]] = None,
        daily: Optional[List[str]] = None,
        minutely_15: Optional[List[str]] = None,
        past_minutely_15: Optional[int] = None,
        forecast_minutely_15: Optional[int] = None,
        start_minutely_15: Optional[str] = None,
        end_minutely_15: Optional[str] = None,
        initial_minutely_15: Optional[int] = None,
        # Model selection
        models: Optional[Union[str, List[str]]] = None,
        # Options
        elevation: Optional[Union[float, List[float]]] = None,
        timezone: Union[str, List[str]] = "UTC",
        temperature_unit: str = "celsius",     # celsius, fahrenheit
        wind_speed_unit: str = "kmh",          # kmh, mph, kn, ms
        precipitation_unit: str = "mm",        # mm, inch
        length_unit: Optional[str] = None,     # metric, imperial
        timeformat: str = "iso8601",           # iso8601, unixtime
        format: str = "json",                  # json, csv, xlsx, flatbuffers
        # Advanced
        cell_selection: Optional[str] = None,  # land, sea, nearest
        temporal_resolution: Optional[str] = None,  # native, hourly, hourly_3, hourly_6
        current_weather: bool = False,
        tilt: Optional[float] = None,          # solar panel tilt deg (0-90)
        azimuth: Optional[float] = None,       # solar panel azimuth deg
        location_id: Optional[Union[int, List[int]]] = None,
        location_information: Optional[str] = None,  # section, omit
        bounding_box: Optional[List[float]] = None,  # [min_lat, min_lon, max_lat, max_lon]
    ) -> dict:
        """
        Main weather forecast endpoint.
        Free tier: up to 16 forecast days, 93 past days.
        Supports batch multi-location by passing lists for lat/lon.
        Supports 15-minute, hourly, and daily aggregations.
        """
        return _get(self._url("forecast"), self._common({
            "latitude": latitude if isinstance(latitude, list) else [latitude],
            "longitude": longitude if isinstance(longitude, list) else [longitude],
            "forecast_days": forecast_days,
            "past_days": past_days if past_days else None,
            "past_hours": past_hours,
            "forecast_hours": forecast_hours,
            "initial_hours": initial_hours,
            "start_date": start_date,
            "end_date": end_date,
            "start_hour": start_hour,
            "end_hour": end_hour,
            "current": current,
            "hourly": hourly,
            "daily": daily,
            "minutely_15": minutely_15,
            "past_minutely_15": past_minutely_15,
            "forecast_minutely_15": forecast_minutely_15,
            "start_minutely_15": start_minutely_15,
            "end_minutely_15": end_minutely_15,
            "initial_minutely_15": initial_minutely_15,
            "models": models,
            "elevation": elevation,
            "timezone": timezone,
            "temperature_unit": temperature_unit,
            "wind_speed_unit": wind_speed_unit,
            "precipitation_unit": precipitation_unit,
            "length_unit": length_unit,
            "timeformat": timeformat,
            "format": format,
            "cell_selection": cell_selection,
            "temporal_resolution": temporal_resolution,
            "current_weather": current_weather if current_weather else None,
            "tilt": tilt,
            "azimuth": azimuth,
            "location_id": location_id,
            "location_information": location_information,
            "bounding_box": bounding_box,
        }), self.timeout)

    # -----------------------------------------------------------------------
    # Model-specific forecast endpoints (shortcuts)
    # -----------------------------------------------------------------------

    def forecast_gfs(self, latitude, longitude, **kwargs) -> dict:
        """GFS / NCEP forecast endpoint (supports 15-minute data)."""
        kwargs.setdefault("models", "gfs_seamless")
        return self._model_forecast("gfs", latitude, longitude, **kwargs)

    def forecast_icon(self, latitude, longitude, **kwargs) -> dict:
        """DWD ICON forecast endpoint."""
        kwargs.setdefault("models", "icon_seamless")
        return self._model_forecast("dwd_icon", latitude, longitude, **kwargs)

    def forecast_ecmwf(self, latitude, longitude, **kwargs) -> dict:
        """ECMWF IFS forecast endpoint."""
        kwargs.setdefault("models", "ecmwf_ifs025")
        return self._model_forecast("ecmwf", latitude, longitude, **kwargs)

    def forecast_meteofrance(self, latitude, longitude, **kwargs) -> dict:
        """MeteoFrance AROME/ARPEGE endpoint (supports 15-minute data)."""
        return self._model_forecast("meteofrance", latitude, longitude, **kwargs)

    def forecast_gem(self, latitude, longitude, **kwargs) -> dict:
        """GEM / CMC (Canada) forecast endpoint."""
        return self._model_forecast("gem", latitude, longitude, **kwargs)

    def forecast_jma(self, latitude, longitude, **kwargs) -> dict:
        """JMA forecast endpoint (Japan)."""
        return self._model_forecast("jma", latitude, longitude, **kwargs)

    def forecast_metno(self, latitude, longitude, **kwargs) -> dict:
        """Met Norway (Nordic) forecast endpoint."""
        return self._model_forecast("metno", latitude, longitude, **kwargs)

    def forecast_bom(self, latitude, longitude, **kwargs) -> dict:
        """BOM ACCESS-G forecast endpoint (Australia)."""
        return self._model_forecast("bom", latitude, longitude, **kwargs)

    def forecast_cma(self, latitude, longitude, **kwargs) -> dict:
        """CMA GRAPES forecast endpoint (China)."""
        return self._model_forecast("cma", latitude, longitude, **kwargs)

    def _model_forecast(self, model_name: str, latitude, longitude, **kwargs) -> dict:
        lat = latitude if isinstance(latitude, list) else [latitude]
        lon = longitude if isinstance(longitude, list) else [longitude]
        params = self._common({"latitude": lat, "longitude": lon})
        params.update({k: v for k, v in kwargs.items() if v is not None})
        return _get(self._url(model_name), params, self.timeout)

    # -----------------------------------------------------------------------
    # Historical Archive API (ERA5 + archive best match, back to 1940)
    # -----------------------------------------------------------------------

    def historical(
        self,
        latitude: Union[float, List[float]],
        longitude: Union[float, List[float]],
        start_date: str,
        end_date: str,
        hourly: Optional[List[str]] = None,
        daily: Optional[List[str]] = None,
        models: Optional[Union[str, List[str]]] = None,
        timezone: Union[str, List[str]] = "UTC",
        temperature_unit: str = "celsius",
        wind_speed_unit: str = "kmh",
        precipitation_unit: str = "mm",
        timeformat: str = "iso8601",
        cell_selection: Optional[str] = None,
    ) -> dict:
        """
        Historical weather archive (ERA5, CERRA back to 1940-01-01).
        Also accessible via archive-api.open-meteo.com/v1/archive.
        """
        return _get(self._url("archive"), self._common({
            "latitude": latitude if isinstance(latitude, list) else [latitude],
            "longitude": longitude if isinstance(longitude, list) else [longitude],
            "start_date": start_date,
            "end_date": end_date,
            "hourly": hourly,
            "daily": daily,
            "models": models,
            "timezone": timezone,
            "temperature_unit": temperature_unit,
            "wind_speed_unit": wind_speed_unit,
            "precipitation_unit": precipitation_unit,
            "timeformat": timeformat,
            "cell_selection": cell_selection,
        }), self.timeout)

    # -----------------------------------------------------------------------
    # Historical Forecast API [SEMI-UNDOCUMENTED]
    # Returns archived actual model forecasts (not reanalysis), back to 2016
    # -----------------------------------------------------------------------

    def historical_forecast(
        self,
        latitude: Union[float, List[float]],
        longitude: Union[float, List[float]],
        start_date: str,
        end_date: str,
        hourly: Optional[List[str]] = None,
        daily: Optional[List[str]] = None,
        models: Optional[Union[str, List[str]]] = None,
        timezone: Union[str, List[str]] = "UTC",
        **kwargs
    ) -> dict:
        """
        [SEMI-UNDOCUMENTED] Returns archived actual model forecast outputs
        (vs. reanalysis). Data back to 2016-01-01. Max 16 forecast days per run.
        Useful for comparing model forecasts vs. reality.
        Host: historical-forecast-api.open-meteo.com
        """
        return _get(self._url("historical_forecast"), self._common({
            "latitude": latitude if isinstance(latitude, list) else [latitude],
            "longitude": longitude if isinstance(longitude, list) else [longitude],
            "start_date": start_date,
            "end_date": end_date,
            "hourly": hourly,
            "daily": daily,
            "models": models,
            "timezone": timezone,
            **{k: v for k, v in kwargs.items() if v is not None},
        }), self.timeout)

    # -----------------------------------------------------------------------
    # Previous Runs API [SEMI-UNDOCUMENTED]
    # Compare current forecast vs previous model runs
    # -----------------------------------------------------------------------

    def previous_runs(
        self,
        latitude: Union[float, List[float]],
        longitude: Union[float, List[float]],
        hourly: Optional[List[str]] = None,
        daily: Optional[List[str]] = None,
        models: Optional[Union[str, List[str]]] = None,
        forecast_days: int = 7,
        past_days: int = 1,
        timezone: Union[str, List[str]] = "UTC",
        **kwargs
    ) -> dict:
        """
        [SEMI-UNDOCUMENTED] Returns data from previous model runs alongside the
        current run. Useful for forecast verification and model comparison.
        Data available from 2016-01-01. Host: previous-runs-api.open-meteo.com
        """
        return _get(self._url("previous_runs"), self._common({
            "latitude": latitude if isinstance(latitude, list) else [latitude],
            "longitude": longitude if isinstance(longitude, list) else [longitude],
            "hourly": hourly,
            "daily": daily,
            "models": models,
            "forecast_days": forecast_days,
            "past_days": past_days,
            "timezone": timezone,
            **{k: v for k, v in kwargs.items() if v is not None},
        }), self.timeout)

    # -----------------------------------------------------------------------
    # Single Runs API [UNDOCUMENTED]
    # Query a specific model initialization (run) time
    # -----------------------------------------------------------------------

    def single_run(
        self,
        latitude: Union[float, List[float]],
        longitude: Union[float, List[float]],
        run: str,
        hourly: Optional[List[str]] = None,
        daily: Optional[List[str]] = None,
        models: Optional[Union[str, List[str]]] = None,
        forecast_days: int = 7,
        timezone: Union[str, List[str]] = "UTC",
        **kwargs
    ) -> dict:
        """
        [UNDOCUMENTED] Query a specific model initialization (run) time.
        The `run` parameter is required: format "2024-01-15T00:00"
        Data available from 2023-01-01. Host: single-runs-api.open-meteo.com
        """
        return _get(self._url("single_runs"), self._common({
            "latitude": latitude if isinstance(latitude, list) else [latitude],
            "longitude": longitude if isinstance(longitude, list) else [longitude],
            "run": run,
            "hourly": hourly,
            "daily": daily,
            "models": models,
            "forecast_days": forecast_days,
            "timezone": timezone,
            **{k: v for k, v in kwargs.items() if v is not None},
        }), self.timeout)

    # -----------------------------------------------------------------------
    # Satellite Radiation API [UNDOCUMENTED]
    # Satellite-derived solar radiation back to 1983
    # -----------------------------------------------------------------------

    def satellite_radiation(
        self,
        latitude: Union[float, List[float]],
        longitude: Union[float, List[float]],
        start_date: str,
        end_date: str,
        hourly: Optional[List[str]] = None,
        models: Optional[Union[str, List[str]]] = None,
        timezone: Union[str, List[str]] = "UTC",
        tilt: Optional[float] = None,
        azimuth: Optional[float] = None,
        **kwargs
    ) -> dict:
        """
        [UNDOCUMENTED] Satellite-derived solar radiation data back to 1983-01-01.
        Models: satellite_radiation_seamless, eumetsat_sarah3,
                eumetsat_lsa_saf_msg, eumetsat_lsa_saf_iodc,
                jma_jaxa_himawari, jma_jaxa_mtg_fci
        Variables: shortwave_radiation, direct_radiation, diffuse_radiation,
                   direct_normal_irradiance, global_tilted_irradiance, sunshine_duration
        Host: satellite-api.open-meteo.com
        """
        return _get(self._url("satellite"), self._common({
            "latitude": latitude if isinstance(latitude, list) else [latitude],
            "longitude": longitude if isinstance(longitude, list) else [longitude],
            "start_date": start_date,
            "end_date": end_date,
            "hourly": hourly,
            "models": models,
            "timezone": timezone,
            "tilt": tilt,
            "azimuth": azimuth,
            **{k: v for k, v in kwargs.items() if v is not None},
        }), self.timeout)

    # -----------------------------------------------------------------------
    # Ensemble Forecast API
    # -----------------------------------------------------------------------

    def ensemble(
        self,
        latitude: Union[float, List[float]],
        longitude: Union[float, List[float]],
        hourly: Optional[List[str]] = None,
        daily: Optional[List[str]] = None,
        models: Optional[Union[str, List[str]]] = None,
        forecast_days: int = 7,
        past_days: int = 0,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        timezone: Union[str, List[str]] = "UTC",
        temperature_unit: str = "celsius",
        wind_speed_unit: str = "kmh",
        precipitation_unit: str = "mm",
        timeformat: str = "iso8601",
        cell_selection: Optional[str] = None,
    ) -> dict:
        """
        Ensemble weather forecasts with multiple model members.
        Models: icon_seamless_eps, ecmwf_ifs025_ensemble, ncep_gefs_seamless,
                gem_global_ensemble, ukmo_global_ensemble_20km, etc.
        Returns separate columns for each ensemble member (e.g. temperature_2m_member01).
        """
        return _get(self._url("ensemble"), self._common({
            "latitude": latitude if isinstance(latitude, list) else [latitude],
            "longitude": longitude if isinstance(longitude, list) else [longitude],
            "hourly": hourly,
            "daily": daily,
            "models": models,
            "forecast_days": forecast_days,
            "past_days": past_days if past_days else None,
            "start_date": start_date,
            "end_date": end_date,
            "timezone": timezone,
            "temperature_unit": temperature_unit,
            "wind_speed_unit": wind_speed_unit,
            "precipitation_unit": precipitation_unit,
            "timeformat": timeformat,
            "cell_selection": cell_selection,
        }), self.timeout)

    # -----------------------------------------------------------------------
    # Marine Weather API
    # -----------------------------------------------------------------------

    def marine(
        self,
        latitude: Union[float, List[float]],
        longitude: Union[float, List[float]],
        current: Optional[List[str]] = None,
        hourly: Optional[List[str]] = None,
        daily: Optional[List[str]] = None,
        minutely_15: Optional[List[str]] = None,
        models: Optional[Union[str, List[str]]] = None,
        forecast_days: int = 7,
        past_days: int = 0,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        timezone: Union[str, List[str]] = "UTC",
        timeformat: str = "iso8601",
        length_unit: Optional[str] = None,
        cell_selection: Optional[str] = "sea",
    ) -> dict:
        """
        Marine weather: waves, swell, sea surface temperature, ocean currents.
        Variables: wave_height, wind_wave_height, swell_wave_height,
                   wave_period, wind_wave_period, wave_direction, etc.
        Models: marine_best_match, ewam, gwam, era5_ocean, ecmwf_wam025,
                ncep_gfswave025, ncep_gefswave025, meteofrance_wave, etc.
        """
        return _get(self._url("marine"), self._common({
            "latitude": latitude if isinstance(latitude, list) else [latitude],
            "longitude": longitude if isinstance(longitude, list) else [longitude],
            "current": current,
            "hourly": hourly,
            "daily": daily,
            "minutely_15": minutely_15,
            "models": models,
            "forecast_days": forecast_days,
            "past_days": past_days if past_days else None,
            "start_date": start_date,
            "end_date": end_date,
            "timezone": timezone,
            "timeformat": timeformat,
            "length_unit": length_unit,
            "cell_selection": cell_selection,
        }), self.timeout)

    # -----------------------------------------------------------------------
    # Air Quality API
    # -----------------------------------------------------------------------

    def air_quality(
        self,
        latitude: Union[float, List[float]],
        longitude: Union[float, List[float]],
        current: Optional[List[str]] = None,
        hourly: Optional[List[str]] = None,
        models: Optional[Union[str, List[str]]] = None,
        domains: Optional[str] = None,      # auto, global, europe
        forecast_days: int = 5,
        past_days: int = 0,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        timezone: Union[str, List[str]] = "UTC",
        timeformat: str = "iso8601",
        cell_selection: Optional[str] = None,
    ) -> dict:
        """
        Air quality forecast (CAMS global + Europe).
        Variables: pm10, pm2_5, carbon_monoxide, nitrogen_dioxide, ozone,
                   sulphur_dioxide, ammonia, aerosol_optical_depth, dust,
                   uv_index, uv_index_clear_sky,
                   european_aqi, us_aqi (and per-pollutant sub-indices),
                   alder_pollen, birch_pollen, grass_pollen, etc.,
                   carbon_dioxide, methane (greenhouse gases - less documented),
                   formaldehyde, glyoxal, peroxyacyl_nitrates, etc.
        History available from 2013-01-01.
        """
        return _get(self._url("air_quality"), self._common({
            "latitude": latitude if isinstance(latitude, list) else [latitude],
            "longitude": longitude if isinstance(longitude, list) else [longitude],
            "current": current,
            "hourly": hourly,
            "models": models,
            "domains": domains,
            "forecast_days": forecast_days,
            "past_days": past_days if past_days else None,
            "start_date": start_date,
            "end_date": end_date,
            "timezone": timezone,
            "timeformat": timeformat,
            "cell_selection": cell_selection,
        }), self.timeout)

    # -----------------------------------------------------------------------
    # Seasonal Forecast API
    # -----------------------------------------------------------------------

    def seasonal(
        self,
        latitude: Union[float, List[float]],
        longitude: Union[float, List[float]],
        daily: Optional[List[str]] = None,
        weekly: Optional[List[str]] = None,
        monthly: Optional[List[str]] = None,
        six_hourly: Optional[List[str]] = None,
        models: Optional[Union[str, List[str]]] = None,
        forecast_days: int = 183,
        timezone: Union[str, List[str]] = "UTC",
        temperature_unit: str = "celsius",
        wind_speed_unit: str = "kmh",
        precipitation_unit: str = "mm",
        timeformat: str = "iso8601",
    ) -> dict:
        """
        Seasonal ensemble forecasts (up to 6-7 months ahead).
        Supports daily, weekly, monthly, and 6-hourly aggregations.
        Models: ecmwf_seasonal_seamless, ecmwf_seas5, ecmwf_ec46
        Weekly variables include anomaly, EFI (extreme forecast index), SOT indices.
        Monthly variables include mean + anomaly pairs.
        """
        return _get(self._url("seasonal"), self._common({
            "latitude": latitude if isinstance(latitude, list) else [latitude],
            "longitude": longitude if isinstance(longitude, list) else [longitude],
            "daily": daily,
            "weekly": weekly,
            "monthly": monthly,
            "six_hourly": six_hourly,
            "models": models,
            "forecast_days": forecast_days,
            "timezone": timezone,
            "temperature_unit": temperature_unit,
            "wind_speed_unit": wind_speed_unit,
            "precipitation_unit": precipitation_unit,
            "timeformat": timeformat,
        }), self.timeout)

    # -----------------------------------------------------------------------
    # Climate Projections API (CMIP6)
    # -----------------------------------------------------------------------

    def climate(
        self,
        latitude: Union[float, List[float]],
        longitude: Union[float, List[float]],
        start_date: str,
        end_date: str,
        daily: Optional[List[str]] = None,
        models: Optional[Union[str, List[str]]] = None,
        temperature_unit: str = "celsius",
        wind_speed_unit: str = "kmh",
        precipitation_unit: str = "mm",
        timeformat: str = "iso8601",
        disable_bias_correction: Optional[bool] = None,
    ) -> dict:
        """
        CMIP6 climate model projections (1950-2050).
        Models: CMCC_CM2_VHR4, FGOALS_f3_H, HiRAM_SIT_HR, MRI_AGCM3_2_S,
                EC_Earth3P_HR, MPI_ESM1_2_XR, NICAM16_8S
        disable_bias_correction: set True to skip ERA5-based bias correction.
        """
        return _get(self._url("climate"), self._common({
            "latitude": latitude if isinstance(latitude, list) else [latitude],
            "longitude": longitude if isinstance(longitude, list) else [longitude],
            "start_date": start_date,
            "end_date": end_date,
            "daily": daily,
            "models": models,
            "temperature_unit": temperature_unit,
            "wind_speed_unit": wind_speed_unit,
            "precipitation_unit": precipitation_unit,
            "timeformat": timeformat,
            "disable_bias_correction": disable_bias_correction,
        }), self.timeout)

    # -----------------------------------------------------------------------
    # Flood / GloFas API
    # -----------------------------------------------------------------------

    def flood(
        self,
        latitude: Union[float, List[float]],
        longitude: Union[float, List[float]],
        daily: Optional[List[str]] = None,
        models: Optional[Union[str, List[str]]] = None,
        forecast_days: int = 92,
        past_days: int = 0,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        ensemble: bool = False,
        timezone: Union[str, List[str]] = "UTC",
        timeformat: str = "iso8601",
        cell_selection: Optional[str] = None,
    ) -> dict:
        """
        GloFas (Global Flood Awareness System) river discharge forecast.
        Variables: river_discharge, river_discharge_mean, river_discharge_min,
                   river_discharge_max, river_discharge_median,
                   river_discharge_p25, river_discharge_p75
        Models: flood_best_match, seamless_v4, forecast_v4, consolidated_v4,
                seamless_v3, forecast_v3, consolidated_v3
        ensemble=True: returns individual ensemble members (51 members)
        History available from 1984-01-01.
        """
        return _get(self._url("flood"), self._common({
            "latitude": latitude if isinstance(latitude, list) else [latitude],
            "longitude": longitude if isinstance(longitude, list) else [longitude],
            "daily": daily,
            "models": models,
            "forecast_days": forecast_days,
            "past_days": past_days if past_days else None,
            "start_date": start_date,
            "end_date": end_date,
            "ensemble": ensemble if ensemble else None,
            "timezone": timezone,
            "timeformat": timeformat,
            "cell_selection": cell_selection,
        }), self.timeout)

    # -----------------------------------------------------------------------
    # Elevation / DEM API
    # -----------------------------------------------------------------------

    def elevation(
        self,
        latitude: Union[float, List[float]],
        longitude: Union[float, List[float]],
    ) -> dict:
        """
        Digital Elevation Model lookup. Returns elevation in meters.
        Supports batch queries (up to hundreds of points per request).
        Returns: {"elevation": [float, ...]}
        """
        lat = latitude if isinstance(latitude, list) else [latitude]
        lon = longitude if isinstance(longitude, list) else [longitude]
        return _get(self._url("elevation"), self._common({
            "latitude": lat,
            "longitude": lon,
        }), self.timeout)

    # -----------------------------------------------------------------------
    # Geocoding API
    # -----------------------------------------------------------------------

    def geocode(
        self,
        name: str,
        count: int = 10,
        language: str = "en",
        format: str = "json",
        country_code: Optional[str] = None,
    ) -> dict:
        """
        Search for locations by name in any language.
        Returns name, lat, lon, elevation, feature_code, timezone, population, postcodes.
        """
        params = self._common({
            "name": name,
            "count": count,
            "language": language,
            "format": format,
        })
        if country_code:
            params["country_code"] = country_code
        return _get(BASE_URLS["geocoding"], params, self.timeout)

    def geocode_by_id(self, location_id: int, language: str = "en") -> dict:
        """
        [UNDOCUMENTED] Get location details by GeoNames ID.
        Returns the same fields as search.
        """
        return _get(BASE_URLS["geocoding_get"], self._common({
            "id": location_id,
            "language": language,
        }), self.timeout)

    # -----------------------------------------------------------------------
    # Bounding Box Query [SEMI-UNDOCUMENTED]
    # -----------------------------------------------------------------------

    def forecast_bbox(
        self,
        min_lat: float,
        min_lon: float,
        max_lat: float,
        max_lon: float,
        hourly: Optional[List[str]] = None,
        daily: Optional[List[str]] = None,
        models: Optional[Union[str, List[str]]] = None,
        forecast_days: int = 7,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        timezone: str = "UTC",
        **kwargs
    ) -> dict:
        """
        [SEMI-UNDOCUMENTED] Spatial bounding box query - returns data for ALL
        grid cells within the box. Only supported for specific models
        (not best_match), e.g.: icon_eu, icon_d2, gfs025, ecmwf_ifs025, etc.
        Returns a JSON array with one element per grid point.
        """
        return _get(self._url("forecast"), self._common({
            "latitude": [min_lat],
            "longitude": [min_lon],
            "bounding_box": [min_lat, min_lon, max_lat, max_lon],
            "hourly": hourly,
            "daily": daily,
            "models": models,
            "forecast_days": forecast_days,
            "start_date": start_date,
            "end_date": end_date,
            "timezone": timezone,
            **{k: v for k, v in kwargs.items() if v is not None},
        }), self.timeout)

    # -----------------------------------------------------------------------
    # Convenience helpers
    # -----------------------------------------------------------------------

    def get_pressure_level_variable(self, variable: str, level: int) -> str:
        """Helper to format pressure-level variable names."""
        return f"{variable}_{level}hPa"

    def get_height_variable(self, variable: str, height_m: int) -> str:
        """Helper to format height-based variable names."""
        return f"{variable}_{height_m}m"

    def get_spread_variable(self, variable: str) -> str:
        """Helper to get ensemble spread variable name."""
        return f"{variable}_spread"

    def get_member_variable(self, variable: str, member: int) -> str:
        """Helper to format ensemble member variable names."""
        return f"{variable}_member{member:02d}"


# ---------------------------------------------------------------------------
# Standalone helper functions
# ---------------------------------------------------------------------------

def get_forecast(
    latitude: float,
    longitude: float,
    variables: List[str] = None,
    daily: List[str] = None,
    days: int = 7,
    **kwargs
) -> dict:
    """Quickstart function for basic forecast."""
    client = OpenMeteoClient()
    return client.forecast(
        latitude=latitude,
        longitude=longitude,
        hourly=variables or ["temperature_2m", "precipitation", "wind_speed_10m"],
        daily=daily,
        forecast_days=days,
        **kwargs
    )


def get_historical(
    latitude: float,
    longitude: float,
    start_date: str,
    end_date: str,
    variables: List[str] = None,
    **kwargs
) -> dict:
    """Quickstart function for historical data."""
    client = OpenMeteoClient()
    return client.historical(
        latitude=latitude,
        longitude=longitude,
        start_date=start_date,
        end_date=end_date,
        hourly=variables or ["temperature_2m", "precipitation", "wind_speed_10m"],
        **kwargs
    )


def get_location(name: str, language: str = "en") -> Optional[dict]:
    """Search for a location and return the top result."""
    client = OpenMeteoClient()
    result = client.geocode(name, count=1, language=language)
    results = result.get("results", [])
    return results[0] if results else None


def build_pressure_level_variables(
    variables: List[str],
    levels: List[int]
) -> List[str]:
    """Build a list of pressure-level variable strings."""
    return [f"{v}_{l}hPa" for v in variables for l in levels]


# ---------------------------------------------------------------------------
# Example usage
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    client = OpenMeteoClient()

    print("=" * 60)
    print("1. Basic 7-day forecast for Berlin")
    print("=" * 60)
    data = client.forecast(
        latitude=52.52,
        longitude=13.41,
        hourly=["temperature_2m", "precipitation", "wind_speed_10m", "weather_code"],
        daily=["temperature_2m_max", "temperature_2m_min", "precipitation_sum", "sunrise", "sunset"],
        current=["temperature_2m", "wind_speed_10m", "weather_code"],
        forecast_days=3,
        timezone="Europe/Berlin",
    )
    print(f"Forecast timezone: {data['timezone']}")
    print(f"Current temp: {data['current']['temperature_2m']}°C")
    print(f"Hourly times (first 3): {data['hourly']['time'][:3]}")
    print()

    print("=" * 60)
    print("2. Historical data for Paris (Jan 2024)")
    print("=" * 60)
    hist = client.historical(
        latitude=48.85,
        longitude=2.35,
        start_date="2024-01-01",
        end_date="2024-01-07",
        daily=["temperature_2m_max", "temperature_2m_min", "precipitation_sum"],
        timezone="Europe/Paris",
    )
    print(f"Dates: {hist['daily']['time']}")
    print(f"Max temps: {hist['daily']['temperature_2m_max']}")
    print()

    print("=" * 60)
    print("3. Air quality with greenhouse gases (Berlin)")
    print("=" * 60)
    aq = client.air_quality(
        latitude=52.52,
        longitude=13.41,
        current=["pm10", "pm2_5", "european_aqi", "us_aqi"],
        hourly=["carbon_dioxide", "methane"],
        forecast_days=2,
    )
    print(f"Current PM10: {aq['current']['pm10']} μg/m³")
    print(f"Current European AQI: {aq['current']['european_aqi']}")
    print()

    print("=" * 60)
    print("4. Marine forecast (North Sea)")
    print("=" * 60)
    marine = client.marine(
        latitude=55.0,
        longitude=4.0,
        hourly=["wave_height", "wave_direction", "wave_period",
                "wind_wave_height", "swell_wave_height"],
        daily=["wave_height_max"],
        forecast_days=3,
    )
    print(f"Marine hourly units: {marine['hourly_units']}")
    print()

    print("=" * 60)
    print("5. Flood forecast (Rhine river)")
    print("=" * 60)
    flood = client.flood(
        latitude=51.86,
        longitude=6.14,
        daily=["river_discharge", "river_discharge_mean", "river_discharge_max"],
        forecast_days=14,
    )
    print(f"Flood units: {flood['daily_units']}")
    print()

    print("=" * 60)
    print("6. Elevation for multiple cities")
    print("=" * 60)
    elev = client.elevation(
        latitude=[52.52, 48.85, 40.71, 35.69, -33.87],
        longitude=[13.41, 2.35, -74.01, 139.69, 151.21],
    )
    print(f"Elevations (m): {elev['elevation']}")
    print()

    print("=" * 60)
    print("7. Geocoding - search for 'Tokyo'")
    print("=" * 60)
    geo = client.geocode("Tokyo", count=1)
    r = geo["results"][0]
    print(f"Name: {r['name']}, Country: {r['country']}")
    print(f"Lat: {r['latitude']}, Lon: {r['longitude']}, Tz: {r['timezone']}")
    print()

    print("=" * 60)
    print("8. Ensemble forecast (ECMWF IFS Ensemble, 14 days)")
    print("=" * 60)
    ens = client.ensemble(
        latitude=52.52,
        longitude=13.41,
        hourly=["temperature_2m"],
        models=["ecmwf_ifs025_ensemble"],
        forecast_days=7,
    )
    hourly_keys = [k for k in ens.get("hourly_units", {}).keys()]
    print(f"Ensemble fields (first 5): {hourly_keys[:5]}")
    member_count = len([k for k in hourly_keys if "member" in k])
    print(f"Number of ensemble members: {member_count}")
    print()

    print("=" * 60)
    print("9. Pressure level variables (500 hPa temperature)")
    print("=" * 60)
    pl = client.forecast(
        latitude=52.52,
        longitude=13.41,
        hourly=["temperature_500hPa", "geopotential_height_500hPa",
                "wind_speed_500hPa", "wind_direction_500hPa"],
        forecast_days=1,
    )
    print(f"500 hPa temp (first value): {pl['hourly']['temperature_500hPa'][0]}°C")
    print()

    print("=" * 60)
    print("10. 15-minute resolution data")
    print("=" * 60)
    m15 = client.forecast(
        latitude=52.52,
        longitude=13.41,
        minutely_15=["temperature_2m", "wind_speed_10m", "shortwave_radiation"],
        forecast_days=1,
    )
    print(f"15-min intervals in day: {len(m15['minutely_15']['time'])}")
    print(f"First 15-min time: {m15['minutely_15']['time'][0]}")
    print()

    print("=" * 60)
    print("11. [UNDOCUMENTED] Single model run query")
    print("=" * 60)
    from datetime import datetime, timedelta
    yesterday = (datetime.utcnow() - timedelta(days=1)).strftime("%Y-%m-%dT00:00")
    try:
        sr = client.single_run(
            latitude=52.52,
            longitude=13.41,
            run=yesterday,
            hourly=["temperature_2m"],
            forecast_days=3,
        )
        print(f"Single run start: {sr['hourly']['time'][0]}")
    except Exception as e:
        print(f"Single run: {e}")
    print()

    print("=" * 60)
    print("12. [UNDOCUMENTED] Satellite radiation data")
    print("=" * 60)
    sat = client.satellite_radiation(
        latitude=48.85,
        longitude=2.35,
        start_date="2024-06-01",
        end_date="2024-06-03",
        hourly=["shortwave_radiation", "direct_radiation", "diffuse_radiation",
                "direct_normal_irradiance", "sunshine_duration"],
        models=["satellite_radiation_seamless"],
    )
    print(f"Satellite radiation variables: {list(sat['hourly_units'].keys())}")
    print()

    print("=" * 60)
    print("13. Climate projection (MRI model, Berlin 2030s)")
    print("=" * 60)
    climate = client.climate(
        latitude=52.52,
        longitude=13.41,
        start_date="2030-01-01",
        end_date="2030-01-31",
        daily=["temperature_2m_max", "temperature_2m_min", "precipitation_sum"],
        models=["MRI_AGCM3_2_S"],
    )
    print(f"Climate projection dates (first 3): {climate['daily']['time'][:3]}")
    print(f"Projected max temps (first 3): {climate['daily']['temperature_2m_max'][:3]}")
    print()

    print("=" * 60)
    print("14. Batch multi-location forecast")
    print("=" * 60)
    batch = client.forecast(
        latitude=[52.52, 48.85, 40.71, 35.69, 55.75],
        longitude=[13.41, 2.35, -74.01, 139.69, 37.62],
        current=["temperature_2m"],
        forecast_days=1,
    )
    if isinstance(batch, list):
        for loc in batch:
            print(f"  lat={loc['latitude']:.2f} lon={loc['longitude']:.2f}: {loc['current']['temperature_2m']}°C")
    print()

    print("=" * 60)
    print("15. Solar panel GTI (tilted irradiance)")
    print("=" * 60)
    solar = client.forecast(
        latitude=48.85,
        longitude=2.35,
        hourly=["global_tilted_irradiance", "global_tilted_irradiance_instant"],
        tilt=35,       # 35 degrees tilt
        azimuth=0,     # south-facing
        forecast_days=1,
    )
    print(f"Tilted irradiance variables: {list(solar['hourly_units'].keys())}")
    print()

    print("All examples completed successfully!")
