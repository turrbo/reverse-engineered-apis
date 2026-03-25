# NOAA Weather Prediction Center (WPC) API Client

Reverse-engineered Python client for `https://www.wpc.ncep.noaa.gov/`

**No authentication required.** All data is public government data.

---

## Quick Start

```bash
pip install requests
python noaa_wpc_client.py   # runs the demo
```

```python
from noaa_wpc_client import WPCClient

client = WPCClient(output_dir="/tmp/wpc_data")

# Get the Short Range Public Discussion
text = client.get_discussion("pmdspd")
print(text[:500])

# Download today's surface analysis
path = client.download_surface_analysis()

# Download Day-1 QPF map
path = client.download_qpf_image(day=1)

# Get ERO GeoJSON for Day 1
data = client.get_ero_geojson(day=1)
```

---

## Discovered API Endpoints

### Surface Analysis Maps

| Product | URL Pattern | Notes |
|---------|------------|-------|
| Current CONUS analysis | `/sfc/namussfc{HH}wbg.gif` | HH = 00,03,06,09,12,15,18,21 |
| Current CONUS (B&W) | `/sfc/namussfc{HH}bw.gif` | |
| CONUS + fronts overlay | `/sfc/usfntsfc{HH}wbg.gif` | |
| Alaska analysis | `/sfc/namaksfc{HH}wbg.gif` | |
| Large Alaska | `/sfc/namak2sfc{HH}wbg.gif` | |
| Latest (no hour) | `/sfc/namussfcwbg.gif` | |
| **Archive** | `/archives/sfc/{YYYY}/namussfc{YYYYMMDD}{HH}.gif` | Back to 2006 |
| Archive with fronts | `/archives/sfc/{YYYY}/namfntsfc{YYYYMMDD}{HH}.gif` | |
| Archive loops | `/archives/sfc/{YYYY}/namusloop_wbg{YYYYMMDD}{HH}.gif` | |

### QPF (Quantitative Precipitation Forecasts)

| Product | URL | Notes |
|---------|-----|-------|
| Day 1 (24hr, filled) | `/qpf/fill_94qwbg.gif` | Color-filled |
| Day 1 (contours only) | `/qpf/94qwbg.gif` | |
| Day 2 (24hr, filled) | `/qpf/fill_98qwbg.gif` | |
| Day 2 (contours only) | `/qpf/98qwbg.gif` | |
| Day 3 (24hr, filled) | `/qpf/fill_99qwbg.gif` | |
| Day 3 (contours only) | `/qpf/99qwbg.gif` | |
| Days 1-2 (48hr total) | `/qpf/d12_fill.gif` | |
| Days 1-3 (72hr total) | `/qpf/d13_fill.gif` | |
| Day 4 (24hr) | `/qpf/day4p24iwbg_fill.gif` | |
| Day 5 (24hr) | `/qpf/day5p24iwbg_fill.gif` | |
| Day 6 (24hr) | `/qpf/day6p24iwbg_fill.gif` | |
| Day 7 (24hr) | `/qpf/day7p24iwbg_fill.gif` | |
| 5-day total | `/qpf/p120i.gif` | 120hr |
| 7-day total | `/qpf/p168i.gif` | 168hr |

**6-hour QPF** (Day 1, hex-coded periods):
| Period | Filled | Contours |
|--------|--------|---------|
| 00-06hr | `/qpf/fill_91ewbg.gif` | `/qpf/91ewbg.gif` |
| 06-12hr | `/qpf/fill_92ewbg.gif` | `/qpf/92ewbg.gif` |
| 12-18hr | `/qpf/fill_93ewbg.gif` | `/qpf/93ewbg.gif` |
| 18-24hr | `/qpf/fill_9eewbg.gif` | `/qpf/9eewbg.gif` |
| 24-30hr | `/qpf/fill_9fewbg.gif` | `/qpf/9fewbg.gif` |

**Dated/time-stamped QPF** (from model run):
```
/qpf/hpcqpf_{YYYYMMDD}{HH}_{period}hr_f{FFF}.gif
```
Example: `/qpf/hpcqpf_2026032500_12hr_f024.gif`

### Excessive Rainfall Outlook (ERO)

| Product | URL |
|---------|-----|
| Day 1 image | `/qpf/94ewbg.gif` |
| Day 2 image | `/qpf/98ewbg.gif` |
| Day 3 image | `/qpf/99ewbg.gif` |
| Day 4 image | `/qpf/ero_d45/images/d4wbg.gif` |
| Day 5 image | `/qpf/ero_d45/images/d5wbg.gif` |
| Day 1 filled | `/qpf/fill_93ewbg.gif` |
| Day 2 filled | `/qpf/fill_94qwbg.gif` |
| Days 1-until | `/qpf/95ep48iwbg_fill.gif` |
| **GeoJSON Day 1** | `/exper/eromap/geojson/Day1_Latest.geojson` |
| **GeoJSON Day 2** | `/exper/eromap/geojson/Day2_Latest.geojson` |
| **GeoJSON Day 3** | `/exper/eromap/geojson/Day3_Latest.geojson` |
| **GeoJSON Day 4** | `/exper/eromap/geojson/Day4_Latest.geojson` |
| **GeoJSON Day 5** | `/exper/eromap/geojson/Day5_Latest.geojson` |
| KMZ Day 1 | `/kml/ero/Day_1_Excessive_Rainfall_Outlook.kmz` |
| KMZ Day 2 | `/kml/ero/Day_2_Excessive_Rainfall_Outlook.kmz` |
| KMZ Day 3 | `/kml/ero/Day_3_Excessive_Rainfall_Outlook.kmz` |
| Shapefile Day 1 | `https://ftp-wpc.ncep.noaa.gov/shapefiles/qpf/excessive/EXCESSIVERAIN_Day1_latest.zip` |
| ERO info (HTML) | `/qpf/web_ero/ero_web_d1_info.php` |
| ERO legend SVG | `/qpf/web_ero/ero_legend.svg` |
| Population table D1 | `/qpf/web_ero/d1_until_poparea_tbl.php` |

**ERO GeoJSON Feature Properties:**
```json
{
  "dn": 0,
  "PRODUCT": "Day 1 Excessive Rainfall Potential Forecast",
  "VALID_TIME": "01Z 03/25/26 - 12Z 03/25/26",
  "OUTLOOK": "None Expected | Marginal | Slight | Moderate | High",
  "ISSUE_TIME": "2026-03-25 00:14:00",
  "START_TIME": "2026-03-25 01:00:00",
  "END_TIME": "2026-03-25 12:00:00",
  "Snippet": "01Z 03/25/26 - 12Z 03/25/26"
}
```

### National Forecast Charts (NOAA Charts)

| Product | URL |
|---------|-----|
| Day 1 PNG (English) | `/NationalForecastChart/staticmaps/noaad1.png` |
| Day 2 PNG | `/NationalForecastChart/staticmaps/noaad2.png` |
| Day 3 PNG | `/NationalForecastChart/staticmaps/noaad3.png` |
| Day 1 PNG (Spanish) | `/NationalForecastChart/staticmaps/sp_noaad1.png` |
| Day 1 GIF | `/noaa/noaad1.gif` |
| Day 1 PDF | `/noaa/noaad1.pdf` |
| Archive | `/archives/noaa/{YYYY}/noaad1_{YYYYMMDD}{HH}.gif` |

### NationalForecastChart Interactive Map Data

Directory: `/NationalForecastChart/mapdata/`

| File | Contents |
|------|---------|
| `qpfD1.json`, `qpfD2.json`, `qpfD3.json` | QPF MultiPolygon geometry |
| `rsnD1.json`, etc. | Weather reason text polygons |
| `snoD1.json`, etc. | Snow polygons |
| `wwD1.json`, etc. | Winter weather polygons |
| `eroD1.json`, etc. | ERO polygon data |
| `svrD1.json`, etc. | Severe weather |
| `trwD1.json`, etc. | Tropical weather |
| `tropical1.json`, etc. | Tropical storm tracks |
| `fronts91f.js`, etc. | Front line data (JS format) |
| `ERODay1.geojson`, etc. | ERO GeoJSON (for map overlay) |
| `FWXDay1.geojson`, etc. | Fire weather |
| `SWODay1.geojson`, etc. | SWO data |

### Winter Weather Products

| Product | URL |
|---------|-----|
| WSSI CONUS map | `/wwd/wssi/images/WSSI_Overall_CONUS.png` |
| WSSI prob f024 | `/wwd/wssi/images/wssi_p_Overall_Minor_f024.png` |
| WSSI prob f{HHH} | `/wwd/wssi/images/wssi_p_{category}_f{HHH}.png` |
| Day 1 composite | `/wwd/day1_composite_sm.jpg` |
| Day 1 snow >=4in | `/wwd/day1_psnow_gt_04_sm.jpg` |
| Day 1 snow >=8in | `/wwd/day1_psnow_gt_08_sm.jpg` |
| Day 1 snow >=12in | `/wwd/day1_psnow_gt_12_sm.jpg` |
| Day 1 ice >=0.25in | `/wwd/day1_pice_gt_25_sm.jpg` |
| Day 4-7 snow >=25% | `/wwd/pwpf_d47/gif/prbww_sn25_DAY4_conus.gif` |

**WSSI categories**: `Overall_Minor`, `Overall_Moderate`, `Overall_Major`, `Overall_Extreme`, `Ground_Blizzard`, `Snow_Ice`, `Wind`, `Cold`

**PWPF (Probabilistic Winter Precipitation Forecasts):**
```
/pwpf_{period}hr/prb_{period}h{ptype}_ge{threshold}_{datecycle}f{FFF}.gif
```
Example: `/pwpf_24hr/prb_24hsnow_ge01_latestf024.gif`

Snow thresholds (24hr): `01`, `02`, `04`, `06`, `08`, `12`, `18` (inches)
Ice thresholds (24hr): `01`, `10`, `25`, `50` (hundredths of inch)

**Winter Weather Shapefiles (FTP):**
```
https://ftp-wpc.ncep.noaa.gov/shapefiles/ww/day{N}/DAY{N}_{PRODUCT}_latest.tar
```
Products: `PSNOW_GT_04`, `PSNOW_GT_08`, `PSNOW_GT_12`, `PICEZ_GT_25`

### Text Discussions

**URL:** `/discussions/hpcdiscussions.php?disc={type}&version={N}&fmt=reg`

| Code | Product | Frequency |
|------|---------|-----------|
| `pmdspd` | Short Range Public Discussion | ~4x/day |
| `pmdepd` | Extended Forecast Discussion | ~2x/day |
| `pmdak` | Alaska Public Discussion | Daily |
| `pmdhi` | Hawaii Public Discussion | Daily |
| `nathilo` | National High/Low Synopsis | Daily |
| `qpferd` | Excessive Rainfall Discussion | When issued |
| `qpfhsd` | Hazardous Weather Outlook | Daily |
| `fxsa20` | Pacific Public Discussion | Daily |
| `fxsa21` | Pacific Extended Discussion | Daily |
| `fxca20` | Caribbean Discussion | Daily |

Previous versions: `&version=1` (1 back), `&version=2` (2 back), etc.

### Mesoscale Precipitation Discussions (MPDs)

| Product | URL |
|---------|-----|
| MPD list page | `/metwatch/metwatch_mpd.php` |
| Latest MPD map | `/metwatch/latest_mdmap.gif` |
| Specific MPD page | `/metwatch/metwatch_mpd_multi.php?md={NNNN}&yr={YYYY}` |
| MPD image | `/metwatch/images/mcd{NNNN}.gif` |
| RSS feed | `/metwatch/mdrss.xml` |

### Medium Range Forecasts (Day 3-7)

| Product | URL |
|---------|-----|
| WPC wx + fronts (f072) | `/medr/display/wpcwx+frontsf072.gif` |
| WPC wx + fronts (f096) | `/medr/display/wpcwx+frontsf096.gif` |
| WPC wx + fronts (f120) | `/medr/display/wpcwx+frontsf120.gif` |
| WPC wx + fronts (f144) | `/medr/display/wpcwx+frontsf144.gif` |
| WPC wx + fronts (f168) | `/medr/display/wpcwx+frontsf168.gif` |
| 5-day forecast (color) | `/medr/5dayfcst_wbg_conus.gif` |
| 5-day forecast (B&W) | `/medr/5dayfcst_bw_conus.gif` |
| 5-day 500mb | `/medr/5dayfcst500_wbg.gif` |
| CONUS map Day3-7 | `/medr/9jhwbg_conus.gif` through `9nhwbg_conus.gif` |

### National Flood Outlook

| Product | URL |
|---------|-----|
| Static map | `/nationalfloodoutlook/finalfop.png` |
| Map with RFC bounds | `/nationalfloodoutlook/finalfop_prt_rfcs.png` |
| Printable | `/nationalfloodoutlook/finalfop_prt.png` |
| **GeoJSON: occurring** | `/nationalfloodoutlook/occurring.geojson` |
| **GeoJSON: likely** | `/nationalfloodoutlook/likely.geojson` |
| **GeoJSON: possible** | `/nationalfloodoutlook/possible.geojson` |

**Flood GeoJSON Feature Properties:** `ID`, `PRODUCT`, `VALID_DATE`, `ISSUE TIME`, `START TIME`, `END TIME`, `SIG_WX_TYPE`, `style`

### Heat Index Forecasts

| Product | URL |
|---------|-----|
| Default 72hr himax | `/heatindex/images/himax_f072.png` |
| Deterministic | `/heatindex/images/{variable}_{date}.png` |
| Probabilistic | `/heatindex/images/{variable}_prb{threshold}_{date}.png` |

Variables: `himax` (max), `hiavg` (avg), `himin` (min)

### Threats & Hazards (Day 3-7)

| Product | URL |
|---------|-----|
| Hazards contour map | `/threats/final/hazards_d3_7_contours.png` |
| Flooding hazards KML | `/threats/final/FloodingHazards.kml` |
| Flooding hazards ZIP | `/threats/final/FloodingHazards.zip` |
| Precipitation KML | `/threats/final/Prcp_D3_7.kml` |
| Temperature KML | `/threats/final/Temp_D3_7.kml` |
| Soils KML | `/threats/final/Soils_D3_7.kml` |
| Wildfires KML | `/threats/final/Wildfires_D3_7.kml` |

### KML/KMZ Products

Base: `/kml/qpf/`

| Product | File |
|---------|------|
| 6hr QPF f00-f06 | `QPF6hr_f00-f06_latest.kmz` |
| 6hr QPF (12 periods, f00-f78) | `QPF6hr_f{SS}-f{EE}_latest.kmz` |
| Day 1 24hr | `QPF24hr_Day1_latest.kmz` |
| Day 2 24hr | `QPF24hr_Day2_latest.kmz` |
| Day 3 24hr | `QPF24hr_Day3_latest.kmz` |
| Days 1-2 48hr | `QPF48hr_Day1-2_latest.kmz` |
| Days 4-5 48hr | `QPF48hr_Day4-5_latest.kmz` |
| Days 6-7 48hr | `QPF48hr_Day6-7_latest.kmz` |
| 72hr Days 1-3 | `QPF72hr_Day1-3_latest.kmz` |
| 120hr Days 1-5 | `QPF120hr_Day1-5_latest.kmz` |
| 168hr Days 1-7 | `QPF168hr_Day1-7_latest.kmz` |

### FTP Shapefiles

Base: `https://ftp-wpc.ncep.noaa.gov/shapefiles/`

| Directory | Contents |
|-----------|---------|
| `qpf/day1/` | QPF 6hr and 24hr shapefiles |
| `qpf/day2/`, `day3/` | Day 2-3 QPF |
| `qpf/day45/`, `day67/` | Extended QPF |
| `qpf/5day/`, `7day/` | Multi-day totals |
| `qpf/excessive/` | ERO shapefiles |
| `ww/day1/`, `ww/day2/`, `ww/day3/` | Winter weather |
| `fop/` | National Flood Outlook shapefiles |
| `noaa_chart/` | National Forecast Chart shapefiles |
| `heatindex/` | Heat index shapefiles |

**Latest ERO shapefiles:**
```
https://ftp-wpc.ncep.noaa.gov/shapefiles/qpf/excessive/EXCESSIVERAIN_Day1_latest.zip
https://ftp-wpc.ncep.noaa.gov/shapefiles/qpf/excessive/EXCESSIVERAIN_Day2_latest.zip
...Day3, Day4, Day5
```

**GRIB2 QPF:**
```
https://ftp.wpc.ncep.noaa.gov/5km_qpf/
```

### ArcGIS MapServer (WPC Precip Hazards)

Base: `https://mapservices.weather.noaa.gov/vector/rest/services/hazards/wpc_precip_hazards/MapServer`

| Layer | Index |
|-------|-------|
| Excessive Rainfall Day 1 | 0 |
| Excessive Rainfall Day 2 | 1 |
| Excessive Rainfall Day 3 | 2 |
| Excessive Rainfall Day 4 | 3 |
| Excessive Rainfall Day 5 | 4 |

**Query endpoint:**
```
{base}/{layer_index}/query?where=1%3D1&outFields=*&outSR=4326&f=geojson
```

### Low Cluster Analysis

| Product | URL |
|---------|-----|
| Latest map | `/lowclusters/lowclusters_latest.png` |

### Basic Wx (NDFD-based) Forecasts

| Product | URL |
|---------|-----|
| Dated 12hr cycle | `/basicwx/{HH}fndfd_init_{YYYYMMDD}{HH}.gif` |

---

## Client API Reference

```python
from noaa_wpc_client import WPCClient

client = WPCClient(output_dir="/path/to/output", timeout=30)
```

### Surface Analysis

```python
# Current analysis (latest synoptic hour)
client.download_surface_analysis()
client.download_surface_analysis(synoptic_hour=12)
client.download_surface_analysis(region="ak")  # Alaska

# With fronts overlay
client.download_surface_analysis_with_fronts(synoptic_hour=0)

# Archived analysis
from datetime import datetime
client.download_archived_surface_analysis(datetime(2026, 3, 24), 12)
```

### QPF

```python
# Daily QPF (24-hour)
client.download_qpf_image(day=1)  # Day 1
client.download_qpf_image(day=2, filled=False)  # Day 2 contours

# Multi-day totals
client.download_qpf_multiday(days=2)  # 48hr Days 1-2
client.download_qpf_total(days=5)     # 120hr Days 1-5

# Hourly QPF
from datetime import datetime
client.download_qpf_hourly(datetime(2026, 3, 25, 0), forecast_hour=24, period_hours=12)
```

### Excessive Rainfall Outlook

```python
# Images
client.download_ero_image(day=1)
client.download_ero_image_filled(day=2)

# GeoJSON (best for data analysis)
data = client.get_ero_geojson(day=1)
print(data['features'][0]['properties']['OUTLOOK'])  # e.g. "Marginal"

# KMZ for Google Earth
client.download_ero_kmz(day=1)

# Shapefile
client.download_ero_shapefile(day=1)

# Issuance metadata
info = client.get_ero_info(day=1)
```

### National Forecast Charts

```python
client.download_national_forecast_chart(day=1, format="png")
client.download_national_forecast_chart(day=1, format="pdf")
client.download_national_forecast_chart(day=1, spanish=True)
```

### Discussions

```python
# Latest short-range discussion
text = client.get_discussion("pmdspd")

# Previous version
text = client.get_discussion("pmdepd", version=1)

# List all available types
types = client.list_discussion_types()
```

### MPDs

```python
# List current MPDs
mpds = client.get_mpd_list()

# Get MPD text
text = client.get_mpd_text(number=63, year=2026)

# Download MPD map
path = client.download_mpd_image(number=63)

# RSS feed
rss = client.get_mpd_rss()
```

### Winter Weather

```python
# WSSI maps
client.download_wssi_map()
client.download_wssi_forecast(forecast_hour=48, category="Overall_Minor")

# Snow/ice probability
client.download_winter_composite(day=1)
client.download_snow_probability(day=1, threshold_inches=8)
client.download_ice_probability(day=1, threshold=25)

# PWPF probabilistic forecasts
client.download_pwpf_image(precip_type="snow", threshold="01", forecast_hour=24)
client.download_pwpf_image(precip_type="icez", threshold="10", forecast_hour=48)
```

### Flood Outlook

```python
client.download_flood_outlook_map()
data = client.get_flood_outlook_geojson("occurring")
data = client.get_flood_outlook_geojson("likely")
data = client.get_flood_outlook_geojson("possible")
```

### ArcGIS MapServer

```python
# Query ERO Day 1 layer
features = client.get_arcgis_ero_layer(day=1)

# Service metadata
info = client.get_arcgis_service_info()
```

### Batch Download

```python
# Download a standard daily package
result = client.download_daily_package()
print(f"Downloaded: {len(result['downloaded'])} files")
print(f"Errors: {len(result['errors'])}")
```

---

## URL Pattern Summary

| Category | Base Pattern |
|----------|-------------|
| Surface analysis | `https://www.wpc.ncep.noaa.gov/sfc/namus sfc{HH}wbg.gif` |
| QPF Day 1-3 | `https://www.wpc.ncep.noaa.gov/qpf/fill_9{X}qwbg.gif` |
| QPF Day 4-7 | `https://www.wpc.ncep.noaa.gov/qpf/day{N}p24iwbg_fill.gif` |
| ERO image | `https://www.wpc.ncep.noaa.gov/qpf/9{X}ewbg.gif` |
| ERO GeoJSON | `https://www.wpc.ncep.noaa.gov/exper/eromap/geojson/Day{N}_Latest.geojson` |
| NFC map | `https://www.wpc.ncep.noaa.gov/NationalForecastChart/staticmaps/noaad{N}.png` |
| Discussions | `https://www.wpc.ncep.noaa.gov/discussions/hpcdiscussions.php?disc={type}` |
| Winter WSSI | `https://www.wpc.ncep.noaa.gov/wwd/wssi/images/WSSI_Overall_CONUS.png` |
| PWPF | `https://www.wpc.ncep.noaa.gov/pwpf_24hr/prb_24hsnow_ge01_latestf024.gif` |
| Flood GeoJSON | `https://www.wpc.ncep.noaa.gov/nationalfloodoutlook/{category}.geojson` |
| MPD image | `https://www.wpc.ncep.noaa.gov/metwatch/images/mcd{NNNN}.gif` |
| KMZ QPF | `https://www.wpc.ncep.noaa.gov/kml/qpf/QPF24hr_Day1_latest.kmz` |
| Shapefile ERO | `https://ftp-wpc.ncep.noaa.gov/shapefiles/qpf/excessive/EXCESSIVERAIN_Day1_latest.zip` |
| ArcGIS ERO | `https://mapservices.weather.noaa.gov/vector/rest/services/hazards/wpc_precip_hazards/MapServer/{0-4}/query?f=geojson` |

---

## Notes

1. **No authentication needed** -- all endpoints are public government data.
2. **Rate limiting** -- WPC does not appear to have strict rate limits, but be respectful. Add delays between bulk requests.
3. **Image availability** -- Some images may return 404 if the forecast period hasn't been issued yet. The `download_daily_package()` method handles this gracefully.
4. **Time zones** -- Analysis times are UTC. Surface analysis maps are issued every 3 hours at 00Z, 03Z, 06Z, etc.
5. **GeoJSON validity** -- The ERO and Flood Outlook GeoJSON endpoints return valid GeoJSON at `application/geo+json`.
6. **NFC mapdata JSON** -- Some files (`qpfD1.json` etc.) are not strictly valid JSON due to encoding issues, but can be read as text for geometry coordinates.
7. **GRIB2 data** -- QPF is available in GRIB2 format at `https://ftp.wpc.ncep.noaa.gov/5km_qpf/`
8. **FTP server** -- The canonical FTP hostname is `ftp-wpc.ncep.noaa.gov` (the `ftp.wpc.ncep.noaa.gov` redirects here).

---

## Dependencies

```bash
pip install requests
```

Optional for GeoJSON/shapefile processing:
```bash
pip install geopandas shapely
```
