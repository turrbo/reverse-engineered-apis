# Tropical Tidbits API Client

Reverse-engineered Python client for [tropicaltidbits.com](https://www.tropicaltidbits.com) - a popular meteorology website specializing in tropical cyclone tracking, numerical weather model visualization, satellite imagery, and oceanographic analysis.

**Last verified:** March 2026
**Author contact (site owner):** levicowan@tropicaltidbits.com

---

## Important Disclaimers

- All endpoints documented here are **unofficial and undocumented**. They may change at any time without notice.
- Respect the site's [Terms of Use](https://www.tropicaltidbits.com/privacy-policy.html). Do **not** use this client for:
  - Heavy automated batch downloading
  - Embedding real-time content on external websites as a persistent fixture
  - Commercial redistribution of content
- For social media/blogs: cite tropicaltidbits.com explicitly
- For special permissions: contact levicowan@tropicaltidbits.com

---

## Installation

No external dependencies required — uses Python 3 standard library only.

```bash
# Copy the client file to your project
cp tropical_tidbits_client.py /your/project/

# Optional: test it immediately
python3 tropical_tidbits_client.py
```

---

## Quick Start

```python
from tropical_tidbits_client import TropicalTidbitsClient

tt = TropicalTidbitsClient()

# Check active tropical storms
storms = tt.get_active_storms()
for storm in storms:
    print(f"{storm['id']}: {storm['name']} — {storm['max_winds_kt']} kt")

# Download a GFS model forecast image
img = tt.download_model_image(
    model="gfs",
    package="mslp_pcpn_frzn",
    region="us",
    fh=24,
    output_path="gfs_us_fh024.png"
)

# Get Atlantic satellite imagery
img = tt.get_latest_satellite_image("atl", "ir", "atlantic_ir.jpg")
```

---

## API Reference

### `TropicalTidbitsClient` (Top-Level Aggregator)

The main entry point. Provides access to all sub-clients via attributes.

```python
tt = TropicalTidbitsClient()
# Sub-clients:
tt.storms      # StormInfoClient
tt.models      # ModelsClient
tt.satellite   # SatelliteClient
tt.surface     # SurfaceAnalysisClient
tt.ocean       # OceanAnalysisClient
tt.hsanalog    # HSAnalogClient
tt.tc_history  # TCHistoryClient
tt.data        # DataFilesClient
```

**Convenience methods:**

| Method | Description |
|--------|-------------|
| `get_active_storms()` | List of current tropical storms/cyclones |
| `download_model_image(model, package, region, fh, ...)` | Download forecast image with optional save |
| `get_latest_satellite_image(region, product, ...)` | Latest satellite image with optional save |

---

### `StormInfoClient`

Access tropical storm/cyclone data and storm-specific graphics.

#### Endpoints Used

| Endpoint | Description |
|----------|-------------|
| `GET /storminfo/` | Active storm information page (HTML) |
| `GET /storminfo/sfcplots/sfcplot_{storm_id}_latest.png` | Marine surface plot (latest) |
| `GET /storminfo/sfcplots/sfcplot_{storm_id}_{YYYYMMDDhh}.png` | Marine surface plot (specific time) |
| `GET /storminfo/{storm_id}_tracks_latest.png` | Model track forecast image |
| `GET /storminfo/{storm_id}_gefs_latest.png` | GEFS ensemble tracks |
| `GET /storminfo/{storm_id}_geps_latest.png` | GEPS ensemble tracks |
| `GET /storminfo/{storm_id}_intensity_latest.png` | Intensity guidance |

#### Methods

```python
client = tt.storms

# Get raw HTML page
html = client.get_storm_page()

# Parse active storms (returns list of dicts)
storms = client.parse_active_storms()
# Returns: [{"id": "09L", "name": "HURRICANE HENRY", "max_winds_kt": 120, ...}]

# Download surface plot (PNG bytes)
img = client.get_surface_plot("09L")          # Latest
img = client.get_surface_plot("09L", "2026092218")  # Specific time

# Download model tracks (PNG bytes)
img = client.get_model_tracks_image("09L", "tracks")    # All model tracks
img = client.get_model_tracks_image("09L", "gefs")      # GEFS ensemble
img = client.get_model_tracks_image("09L", "geps")      # GEPS ensemble
img = client.get_model_tracks_image("09L", "intensity") # Intensity guidance
```

#### Storm ID Format

Storm IDs follow the ATCF convention:
- `09L` — 9th named storm in the Atlantic basin
- `03E` — 3rd named storm in the East Pacific
- `27P` — 27th named storm in the South Pacific
- Basin codes: `L`=Atlantic, `E`=East Pacific, `C`=Central Pacific, `W`=West Pacific, `P`=South Pacific, `B`=Bay of Bengal, `A`=Arabian Sea, `S`=South Indian

---

### `ModelsClient`

Access numerical weather prediction model imagery.

#### Core Image URL Pattern

```
https://www.tropicaltidbits.com/analysis/models/{model}/{runtime}/{model}_{package}_{region}_{index}.png
```

Where `{index}` is a 1-based sequential number corresponding to a forecast hour. The mapping of index → forecast hour is available from the page's `jsReloadInfo` script block.

**Important:** A `Referer: https://www.tropicaltidbits.com/analysis/models/` header is required.

#### Endpoints Used

| Endpoint | Description |
|----------|-------------|
| `GET /analysis/models/?model={m}&region={r}&pkg={p}&runtime={rt}&fh={fh}` | Model page with jsReloadInfo (image URL list) |
| `GET /analysis/models/{model}/{runtime}/{model}_{package}_{region}_{index}.png` | Model forecast image |
| `GET /analysis/models/sounding_data_times.json` | JSON index of available sounding data |
| `GET /analysis/models/sounding/?model={m}&runtime={rt}&fh={fh}&lat={lat}&lon={lon}&...` | Skew-T sounding image (HTML fragment) |
| `GET /analysis/models/sounding/images/{model}_{runtime}_fh{fh}_sounding_{lat}_{lon}.png` | Sounding PNG image |
| `GET /analysis/models/xsection/?model={m}&runtime={rt}&fh={fh}&p0={lat,lon}&p1={lat,lon}&type={t}&tc={tc}` | Vertical cross section (HTML fragment) |

#### Methods

```python
client = tt.models

# Get full metadata for a model run (parses jsReloadInfo)
meta = client.get_model_metadata("gfs", "us", "mslp_pcpn_frzn")
# meta = {
#   "model": "gfs",
#   "runtime": "2026032418",
#   "img_fh": [6, 12, 18, 24, ...384],
#   "img_urls": ["gfs/2026032418/gfs_mslp_pcpn_frzn_us_1.png", ...],
#   "run_image_urls": {"2026032418": {6: "gfs/.../..._1.png", ...}},
#   "base_url": "https://www.tropicaltidbits.com/analysis/models/"
# }

# Download image by forecast hour (auto-resolves index)
img = client.get_model_image_by_fh("gfs", "2026032418", "mslp_pcpn_frzn", "us", 24)

# Download image by index directly
img = client.get_model_image("gfs", "2026032418", "mslp_pcpn_frzn", "us", 4)

# Sounding data availability
times = client.get_sounding_data_times()  # JSON: {model: {runtime: [fh_list]}}

# Request a sounding (returns HTML fragment with img tag)
html = client.get_sounding("gfs", "2026032418", 24, lat=29.0, lon=-90.0)
img_url = client.parse_sounding_response(html)
# img_url = "/analysis/models/sounding/images/gfs_2026032418_fh24_sounding_29.00N_90.00W.png"

# Download sounding image directly
img = client.get_sounding_image("gfs", "2026032418", 24, 29.0, -90.0)

# Area-averaged sounding (domain = [[lat1,lon1],[lat2,lon2]])
html = client.get_sounding("gfs", "2026032418", 24, 0, 0, domain=[[20,-100],[35,-70]])

# Cross section
html = client.get_cross_section(
    "gfs", "2026032418", 24,
    p0=(30.0, -90.0), p1=(45.0, -70.0),
    xsection_type="RH and Omega"
)
img_url = client.parse_xsection_response(html)
```

#### Available Models

| Category | Models |
|----------|--------|
| Global deterministic | `gfs`, `ecmwf`, `ec-aifs`, `aigfs`, `gem`, `icon`, `jma` |
| Global ensemble | `eps` (ECMWF), `gfs-ens` (GEFS), `gem-ens` (GEPS) |
| Mesoscale | `nam`, `namconus`, `nam3km`, `hrrr`, `fv3-hires`, `wrf-arw`, `wrf-arw2`, `rgem`, `hrdps` |
| Hurricane | `hwrf`, `hwrf-p`, `hafsa`, `hafsa-p`, `hafsb`, `hafsb-p` |
| Climate | `cfs-avg`, `cfs-mon`, `cansips`, `nmme` |

#### Available Packages (Products)

| Category | Packages |
|----------|---------|
| Precipitation/Moisture | `mslp_pcpn`, `mslp_pcpn_frzn`, `apcpn24`, `apcpn`, `asnow`, `asnow24`, `mslp_pwat`, `midRH`, `Td2m`, `ref_frzn` |
| Lower dynamics | `temp_adv_fgen_700`, `temp_adv_fgen_850`, `z700_vort`, `z850_vort`, `mslp_uv850`, `mslp_wind`, `ow850`, `mslptrend`, `mslpa` |
| Upper dynamics | `DTpres`, `upperforcing`, `pv330K`, `isen300K`, `isen290K`, `uv250`, `z500_vort`, `z500_mslp`, `z500a`, `z500trend`, `ir` |
| Thermodynamics | `cape`, `T700`, `T850`, `T850a`, `T2m`, `T2m_contour`, `T2ma` |

#### Available Regions

| Code | Description | Code | Description |
|------|-------------|------|-------------|
| `us` | CONUS | `global` | Global |
| `nwus` | Northwest U.S. | `nhem` | Northern Hemisphere |
| `neus` | Northeast U.S. | `atl` | Atlantic Wide |
| `seus` | Southeast U.S. | `watl` | Western Atlantic |
| `swus` | Southwest U.S. | `eatl` | Eastern Atlantic |
| `wus` | Western U.S. | `epac` | Eastern Pacific |
| `eus` | Eastern U.S. | `cpac` | Central Pacific |
| `ncus` | North-Central U.S. | `wpac` | Western Pacific |
| `scus` | South-Central U.S. | `io` | Indian Ocean |
| `ak` | Alaska | `india` | Bay of Bengal |
| `namer` | North America | `aus` | Australia |
| `samer` | South America | `eu` | Europe |

---

### `SatelliteClient`

Access satellite imagery loops from GOES-19, GOES-18, and Himawari-9.

#### Satellite Image CDN URL Pattern

```
# Regional images:
https://olorin.tropicaltidbits.com/satimages/{satellite}_{product}_{region}_{YYYYMMDDhhmm}.jpg

# TC Floater images (storm-following):
https://olorin.tropicaltidbits.com/satimages/{satellite}_{product}_{storm_id}_{YYYYMMDDhhmm}_lat{lat}-lon{lon}.jpg
```

Satellites: `goes19` (East), `goes18` (West), `himawari9` (West Pacific)

#### Endpoints Used

| Endpoint | Description |
|----------|-------------|
| `GET /sat/` | Satellite imagery index page |
| `GET /sat/satlooper.php?region={r}&product={p}` | Satellite loop page (image URL list in JS) |
| `GET https://olorin.tropicaltidbits.com/satimages/{filename}.jpg` | Satellite image CDN |

#### Methods

```python
client = tt.satellite

# Get all available regions and products
regions = client.parse_satellite_regions()

# Get loop page and extract image URLs for a region
urls = client.parse_sat_image_urls("atl", "ir")
# Returns list of full CDN URLs: ["https://olorin.../goes19_ir_atl_202603250000.jpg", ...]

# Download latest image
img = client.get_latest_sat_image("atl", "ir")        # Atlantic IR
img = client.get_latest_sat_image("epac", "vis")      # East Pacific Visible
img = client.get_latest_sat_image("27P", "wv_mid")    # TC 27P water vapor

# Build URL manually
url = client.build_sat_image_url("goes19", "ir", "atl", "202603250215")
url = client.build_sat_image_url("himawari9", "ir", "27P", "202603250210", lat=-17.4, lon=120.0)

# Download by URL
img = client.get_sat_image_by_url(url)
```

#### Available Products

| Code | Description |
|------|-------------|
| `ir` | Longwave IR (2 km) |
| `dvorak` | Longwave IR [Dvorak] (2 km) |
| `vis` | Visible Hi-Res (0.5 km) |
| `vis_swir` | Visible / Shortwave IR (2 km) |
| `truecolor` | True Color (2 km) |
| `wv_mid` | Water Vapor 6.9 μm (2 km) |
| `wv_rgb` | Water Vapor RGB (2 km) |

#### Available Satellite Regions

| Category | Regions |
|----------|---------|
| TC Floaters | Named by ATCF storm ID (e.g., `27P`, `09L`) |
| Meso sectors | `goes19-meso1`, `goes19-meso2`, `goes18-meso1`, `goes18-meso2`, `himawari9-meso` |
| Atlantic | `atlpac-wide`, `atl`, `gom`, `nwatl`, `watl`, `catl`, `eatl` |
| Pacific | `epac`, `cpac` |
| Land | `us`, `ak`, `hawaii` |

---

### `SurfaceAnalysisClient`

Surface observation plots and pressure change analysis.

#### Endpoints Used

| Endpoint | Description |
|----------|-------------|
| `GET /analysis/sfcplots/sfcplot_latest.png` | Latest Tropical Atlantic surface plot |
| `GET /analysis/sfcplots/sfcplot_{YYYYMMDDhh}.png` | Historical surface plot |
| `GET /analysis/sfcplots/preschange_{region}_latest.png` | Latest pressure change plot |
| `GET /storminfo/sfcplots/sfcplot_{storm_id}_latest.png` | Storm-specific surface plot |

```python
client = tt.surface

# Tropical Atlantic surface observation plot
img = client.get_tropical_sfcplot()                      # Latest
img = client.get_tropical_sfcplot("2026032502")          # Specific time

# Pressure change plots
img = client.get_pressure_change_plot("watl")            # Western Atlantic
img = client.get_pressure_change_plot("eatl")            # Eastern Atlantic

# Storm surface plot
img = client.get_storm_sfcplot("09L")
```

---

### `OceanAnalysisClient`

Sea surface temperature and ENSO index data.

#### Endpoints Used

| Endpoint | Description |
|----------|-------------|
| `GET /analysis/ocean/cdas-sflux_sst_{region}_1.png` | SST map |
| `GET /analysis/ocean/cdas-sflux_ssta_{region}_1.png` | SST Anomaly map |
| `GET /analysis/ocean/cdas-sflux_ssta7diff_{region}_1.png` | 7-day SSTA change |
| `GET /analysis/ocean/cdas-sflux_ssta_relative_{region}_1.png` | SSTA vs global mean |
| `GET /analysis/ocean/{region}.png` | ENSO time series |

```python
client = tt.ocean

# SST maps (region options: global, atl, watl, eatl, epac, cpac, wpac, swpac, aus, io, samer)
img = client.get_sst_map("atl")            # Atlantic SST
img = client.get_ssta_map("global")        # Global SSTA
img = client.get_ssta_7day_change("epac")  # E.Pac 7-day SSTA change

# ENSO time series (region options: nino34, nino3, nino4, nino12, natlssta, mdrssta, ...)
img = client.get_enso_timeseries("nino34")
img = client.get_enso_timeseries("mdrssta")  # Atlantic MDR SSTA
```

---

### `HSAnalogClient`

Hurricane season SST-based analog years.

```python
client = tt.hsanalog

# Get top analog years and scores
analogs = client.parse_top_analogs()
# [{"year": 2017, "score": 0.28}, {"year": 1974, "score": 0.25}, ...]

# Download images
img = client.get_current_ssta_analysis()    # Current CDAS SSTA pattern
img = client.get_analog_mean_image()         # Mean track/intensity of analogs
img = client.get_analog_year_ssta(1)         # SSTA for top analog year
img = client.get_analog_year_ssta(2)         # SSTA for 2nd analog year
```

---

### `TCHistoryClient`

Historical tropical cyclone track maps from IBTrACS.

#### Endpoints Used

| Endpoint | Description |
|----------|-------------|
| `GET /data/TC/{basin}/tracks/{year}.png` | Annual track map for a basin |
| `GET /data/TC/TCfreq_global_1979-2012.png` | TC frequency climatology |
| `GET /data/TC/cat3-freq_global_1979-2012.png` | Cat 3+ frequency |
| `GET /data/TC/spatialACE_global_1979-2012.png` | Spatial ACE climatology |

```python
client = tt.tc_history

# Annual track maps
# Basin codes: NA, EP, CP, WP, NI, SI, SP, AU
img = client.get_track_map("NA", 2005)  # Atlantic 2005 (year of Katrina)
img = client.get_track_map("WP", 2013)  # West Pacific 2013

# Climatology maps
img = client.get_global_frequency_map("all")       # TC frequency
img = client.get_global_frequency_map("cat3")      # Cat 3+ frequency
img = client.get_global_frequency_map("ace")       # ACE distribution
img = client.get_global_frequency_map("intensity") # Average intensity
```

---

### `DataFilesClient`

Static data files.

```python
client = tt.data

# NHC model acronym reference list
model_list_text = client.get_nhc_model_list()
# Plain text file explaining all TC model acronyms (OFCL, GEFS, HWRF, etc.)
```

---

## Data Format Details

### Model Page URL Structure

When you request a model page, the server returns HTML containing an embedded `<script id="jsReloadInfo">` block. This contains JavaScript assignments that initialize the `APP` object with:

```javascript
APP.imgURLs = ['gfs/2026032418/gfs_mslp_pcpn_frzn_us_1.png', ...64 items...];
APP.imgFH = [6, 12, 18, 24, 30, 36, 42, 48, ..., 384];  // forecast hours
APP.runtime = '2026032418';
APP.model = 'gfs';
APP.region = 'us';
APP.pkg = 'mslp_pcpn_frzn';
APP.runImageURLs = {'2026032418': {6: 'gfs/.../...1.png', 12: 'gfs/.../...2.png', ...}};
APP.validImageURLs = {6: ['gfs/2026031718/...', 'gfs/2026031800/...', ...], ...};
```

The `imgURLs` list maps directly to `imgFH` by index. To get the image for fh=24:
1. Find `index_in_list = imgFH.index(24)` (0-based)
2. The filename is `imgURLs[index_in_list]` (which has 1-based index in filename)
3. Full URL = `https://www.tropicaltidbits.com/analysis/models/` + `imgURLs[index_in_list]`

### Sounding URL Structure

```
/analysis/models/sounding/?model={m}&runtime={rt}&fh={fh}&lat={lat}&lon={lon}&stationID=&tc=&mode=sounding
```

Response is an HTML fragment like:
```html
<img id="sounding-image" src="/analysis/models/sounding/images/gfs_2026032418_fh24_sounding_29.00N_90.00W.png" alt="gfs sounding">
```

Image filename pattern: `{model}_{runtime}_fh{fh}_sounding_{lat}_{lon}.png`

### Cross Section URL Structure

```
/analysis/models/xsection/?model={m}&runtime={rt}&fh={fh}&p0={lat},{lon}&p1={lat},{lon}&type={type}&tc={tc}
```

### Satellite Image CDN

Images are served from `https://olorin.tropicaltidbits.com/satimages/` with CORS headers:
```
Access-Control-Allow-Origin: https://www.tropicaltidbits.com
```

The images are accessible without authentication but require the request to come from (or appear to come from) a browser.

---

## Rate Limiting & Best Practices

1. **Use reasonable delays** between requests (1-2 seconds between batches)
2. **Cache metadata** — the `get_model_metadata()` call fetches the full model page; cache the result rather than re-fetching
3. **Check `sounding_data_times.json`** before requesting soundings to verify availability
4. **Use `_latest.png` variants** when you just want current data
5. **Batch by model run** — images for the same model run are served from the same server path

---

## Complete Working Example

```python
#!/usr/bin/env python3
"""
Example: Download a full GFS model loop and save all images.
"""
import os
from tropical_tidbits_client import TropicalTidbitsClient, ModelsClient

tt = TropicalTidbitsClient()
mc = tt.models

# Get metadata for latest GFS run
meta = mc.get_model_metadata("gfs", "us", "mslp_pcpn_frzn")
runtime = meta["runtime"]
print(f"GFS Runtime: {runtime}")
print(f"Available FH: {meta['img_fh']}")

# Create output directory
os.makedirs(f"gfs_{runtime}", exist_ok=True)

# Download first 10 forecast hours
base_url = meta["base_url"]
for i, (fh, url) in enumerate(zip(meta["img_fh"][:10], meta["img_urls"][:10])):
    full_url = base_url + url
    print(f"Downloading FH{fh:03d}...")
    img = mc._make_request_direct(full_url)  # Or use requests library
    with open(f"gfs_{runtime}/fh{fh:03d}.png", "wb") as f:
        f.write(img)
    time.sleep(1)  # Be polite

print("Done!")
```

```python
#!/usr/bin/env python3
"""
Example: Monitor Atlantic satellite imagery.
"""
import time
from tropical_tidbits_client import TropicalTidbitsClient

tt = TropicalTidbitsClient()

while True:
    urls = tt.satellite.parse_sat_image_urls("atl", "ir")
    latest = urls[-1] if urls else None
    if latest:
        print(f"Latest Atlantic IR: {latest}")
        img = tt.satellite.get_sat_image_by_url(latest)
        with open("atlantic_ir_latest.jpg", "wb") as f:
            f.write(img)
    time.sleep(300)  # Update every 5 minutes
```

---

## Endpoint Summary Table

| Section | Endpoint | Auth Required |
|---------|----------|---------------|
| Storm Info | `GET /storminfo/` | No |
| Storm Surface Plot | `GET /storminfo/sfcplots/sfcplot_{id}_latest.png` | No (Referer helpful) |
| Storm Track Plot | `GET /storminfo/{id}_tracks_latest.png` | No |
| Models Page | `GET /analysis/models/?model=...` | No |
| Model Image | `GET /analysis/models/{m}/{rt}/{filename}.png` | Referer required |
| Sounding Times JSON | `GET /analysis/models/sounding_data_times.json` | Referer helpful |
| Sounding (HTML) | `GET /analysis/models/sounding/?model=...` | Referer helpful |
| Sounding Image | `GET /analysis/models/sounding/images/{filename}.png` | Referer helpful |
| Cross Section | `GET /analysis/models/xsection/?...` | Referer helpful |
| Satellite Index | `GET /sat/` | No |
| Sat Loop Page | `GET /sat/satlooper.php?region=...` | No |
| Sat Image CDN | `GET https://olorin.tropicaltidbits.com/satimages/{filename}.jpg` | No |
| Surface Plot (tropical) | `GET /analysis/sfcplots/sfcplot_latest.png` | Referer helpful |
| Pressure Change | `GET /analysis/sfcplots/preschange_{region}_latest.png` | Referer helpful |
| Ocean SST | `GET /analysis/ocean/cdas-sflux_sst_{region}_1.png` | Referer helpful |
| Ocean SSTA | `GET /analysis/ocean/cdas-sflux_ssta_{region}_1.png` | Referer helpful |
| HS Analogs | `GET /analysis/hsanalog/cdas_anl.png` | Referer helpful |
| TC Track Maps | `GET /data/TC/{basin}/tracks/{year}.png` | No |
| NHC Model List | `GET /data/nhc_model_list.txt` | No |

*"Referer helpful" means the request succeeds either way, but sending `Referer: https://www.tropicaltidbits.com/...` mimics browser behavior and is less likely to be blocked.*

---

## Changelog

- **v1.0 (March 2026)**: Initial release. Discovered and documented all major API endpoints.

---

*This client was created by reverse-engineering the public-facing JavaScript and HTML of tropicaltidbits.com for educational and research purposes.*
