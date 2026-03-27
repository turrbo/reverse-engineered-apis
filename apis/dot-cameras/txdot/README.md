# TxDOT / DriveTexas Traffic Camera & Road Conditions API Client

A reverse-engineered Python client for the Texas Department of Transportation
(TxDOT) traffic data system powering [DriveTexas.org](https://drivetexas.org).
Built with Python stdlib only — no third-party dependencies required.

---

## Table of Contents

1. [Background & Architecture](#background--architecture)
2. [API Discovery](#api-discovery)
3. [Discovered Endpoints](#discovered-endpoints)
4. [Data Tables & Schemas](#data-tables--schemas)
5. [Authentication](#authentication)
6. [Camera Stream URLs](#camera-stream-urls)
7. [Quick Start](#quick-start)
8. [CLI Reference](#cli-reference)
9. [Python API Reference](#python-api-reference)
10. [Pagination](#pagination)
11. [Known Limitations](#known-limitations)
12. [Legal Notes](#legal-notes)

---

## Background & Architecture

DriveTexas.org is a React/Redux single-page application built and maintained
by AppGeo on behalf of the Texas Department of Transportation.  The frontend
is hosted at `drivetexas.org` and backed by **MapLarge** — a commercial
geospatial data platform deployed at `dtx-e-cdn.maplarge.com`.

All traffic data (cameras, conditions, flood gauges, contraflow routes) is
served through a single generic MapLarge JSON API endpoint.  The site uses
Google Maps for the map layer and SkyVDN for camera video streaming.

### Component Map

```
┌─────────────────────────────────────┐
│          drivetexas.org             │  React/Redux SPA
│  (main.766816ea.js ~1.5MB bundle)   │
└────────────┬────────────────────────┘
             │ CORS-gated API calls
             ▼
┌─────────────────────────────────────┐
│   dtx-e-cdn.maplarge.com            │  MapLarge geospatial platform
│   /Api/ProcessDirect                │  (AppGeo account "appgeo")
└─────────────────────────────────────┘
             │ camera stream URLs
             ▼
┌─────────────────────────────────────┐
│   s70.us-east-1.skyvdn.com          │  SkyVDN streaming CDN
│   HLS / RTSP / RTMP streams         │
└─────────────────────────────────────┘
             │ GCS config
             ▼
┌─────────────────────────────────────┐
│  storage.googleapis.com/drivetexas  │  Google Cloud Storage
│  /info.json                         │  (site config + splash screens)
└─────────────────────────────────────┘
```

---

## API Discovery

The API was reverse-engineered by:

1. **Fetching the React JS bundle** (`https://drivetexas.org/static/js/main.766816ea.js`)
   and searching for API host strings, environment variables, and fetch calls.

2. **Extracting React environment constants** embedded at build time:
   ```js
   REACT_APP_ML_HOST:        "dtx-e-cdn.maplarge.com"
   REACT_APP_ACCOUNT:        "appgeo"
   REACT_APP_CAMERA_TABLE:   "cameraPoint"
   REACT_APP_SUBDOMAINS:     "8"
   REACT_APP_GMAPS_API_KEY:  "AIzaSyClq6IkuY6poYuCKjhs8WnSsdQzbNursDM"
   REACT_APP_CLOUD_STORAGE_BUCKET: "drivetexas"
   ```

3. **Tracing the `query()` method** in the MapLarge client library embedded
   in the bundle:
   ```js
   query(e) {
       var t = o({request: JSON.stringify(e)});
       var n = `https://${this.host}/Api/ProcessDirect?${t}`;
       return i(n).then(e => this.transposeResp(e));
   }
   ```

4. **Tracing the camera display component** (`lT` component):
   ```js
   const { httpsurl: t, description: n } = v(Ar);
   const s = {
       sources: [{ src: t, type: "application/x-mpegURL" }]
   };
   ```
   Confirming `httpsurl` is the HLS stream URL played by Video.js.

5. **Live testing** against the MapLarge endpoint, discovering:
   - CORS requires `Origin: https://drivetexas.org`
   - Server-side `where` filtering returns HTTP 500 (filtering is client-side only)
   - Pagination via `start` offset works correctly

---

## Discovered Endpoints

### Primary Data API

```
GET https://dtx-e-cdn.maplarge.com/Api/ProcessDirect?request=<JSON>
```

**Required headers:**
```
Origin:  https://drivetexas.org
Referer: https://drivetexas.org/
```

**Query parameter:** `request` — URL-encoded JSON with this shape:

```json
{
  "action": "table/query",
  "query": {
    "sqlselect": ["field1", "field2"],
    "table":     "appgeo/<TABLE_NAME>",
    "take":      500,
    "start":     0
  }
}
```

**Response shape:**

```json
{
  "id":                "0b348d9c...",
  "success":           true,
  "processingComplete": true,
  "isCached":          false,
  "authorized":        true,
  "errors":            [],
  "timestamp":         1774642167.0,
  "data": {
    "data": {
      "fieldName1": ["value1", "value2", ...],
      "fieldName2": ["value1", "value2", ...]
    },
    "totals": { "Records": 3410 },
    "tablename": "appgeo/cameraPoint/..."
  },
  "core":           "ML",
  "actionCategory": "table",
  "actionVerb":     "query"
}
```

Note: data is returned as **columnar arrays** (parallel lists by field name),
not as a list of row objects.

### Site Configuration

```
GET https://storage.googleapis.com/drivetexas/info.json
```

Returns gzip-compressed JSON:

```json
{
  "working":      true,
  "splashscreen": "...",
  "showing":      3,
  "deactivated":  [],
  "date":         1769782199959,
  "modal":        true
}
```

### Map Tile API (read-only, requires hash)

```
GET https://dtx-e-cdn.maplarge.com/Api/ProcessRequest
    ?hash=<LAYER_HASH>
    &uParams=x:<tile_x>;y:<tile_y>;z:<zoom>;action:tile%2Fgettile
```

The hash is generated by the frontend from a layer configuration object.
Tile rendering is used for the map overlay, not needed for raw data access.

### UTFGrid Hover Data

```
POST https://dtx-e-cdn.maplarge.com/Api/ProcessRequest
     hash=<LAYER_HASH>
     &uParams=x:<tx>;y:<ty>;z:<z>;label:<fields>;action:tile/hovergrid
```

Used to retrieve data when the user hovers over map tiles.

---

## Data Tables & Schemas

All tables live under the `appgeo` account on MapLarge.

### `cameraPoint` — 3,410 records

Live traffic camera locations and stream URLs.

| Field          | Type    | Description                                          |
|----------------|---------|------------------------------------------------------|
| `name`         | string  | Unique camera ID, e.g. `TX_HOU_1002`                 |
| `description`  | string  | Human-readable location, e.g. `IH-45 North @ Calvary` |
| `jurisdiction` | string  | TxDOT district city (see districts below)            |
| `route`        | string  | Primary route, e.g. `IH45`, `US0290`, `FM1709`       |
| `direction`    | string  | Travel direction (`East`, `North`, etc.) — often empty |
| `mrm`          | float   | Milepost reference marker                            |
| `active`       | int     | `1` = active stream, `0` = offline                   |
| `problemstream`| int     | Non-zero if streaming problem detected               |
| `lastUpdated`  | int     | Epoch milliseconds of last data refresh              |
| `id`           | int     | Internal numeric ID                                  |
| `imageurl`     | string  | Snapshot PNG URL (contains `localhost` — internal)   |
| `httpsurl`     | string  | **HLS stream URL** (`.m3u8`) — primary playback URL  |
| `iosurl`       | string  | iOS HLS URL (identical to `httpsurl`)                |
| `rtspurl`      | string  | RTSP stream URL (port 554)                           |
| `rtmpurl`      | string  | RTMP stream URL (port 1935)                          |
| `clspsurl`     | string  | SkyVDN CLSPS proprietary protocol URL                |
| `prerollurl`   | string  | HLS pre-roll/buffer segment URL                      |
| `deviceid`     | int     | Hardware device identifier                           |
| `distance`     | string  | Distance annotation (usually empty)                  |

**Camera jurisdictions (districts):**

| District        | Count |
|-----------------|-------|
| Houston         | 859   |
| Dallas          | 754   |
| Ft Worth        | 332   |
| San Antonio     | 297   |
| Austin          | 216   |
| El Paso         | 202   |
| Beaumont        | 109   |
| Laredo          | 107   |
| Waco            | 81    |
| Odessa          | 62    |
| Corpus Christi  | 58    |
| Lubbock         | 55    |
| San Angelo      | 44    |
| Abilene         | 36    |
| Pharr           | 31    |
| Atlanta         | 29    |
| Paris           | 26    |
| Amarillo        | 24    |
| Bryan           | 21    |
| Yoakum          | 17    |
| Tyler           | 17    |
| Wichita Falls   | 15    |
| Lufkin          | 8     |
| Childress       | 6     |
| Brownwood       | 4     |
| **Total**       | **3,410** |

---

### `conditionsPoint` — ~664 records (live)

Current road conditions at point locations.

### `conditionsLine` — ~659 records (live)

Current road conditions along line segments.

**Shared condition fields:**

| Field                | Type    | Description                                         |
|----------------------|---------|-----------------------------------------------------|
| `HCRSCONDID`         | string  | Internal HCRS condition identifier                  |
| `RTENM`              | string  | Route name, e.g. `IH0035`, `US0290`                 |
| `RDWAYNM`            | string  | Roadway name                                        |
| `CONDDSCR`           | string  | Full condition narrative text (may contain HTML)    |
| `CONDSTARTTS`        | int     | Start timestamp (epoch milliseconds)                |
| `CONDENDTS`          | int     | End timestamp (epoch milliseconds, 0 = no end)      |
| `CNSTRNTTYPECD`      | string  | Type code: `C`=Construction, `A`=Accident, `D`=Damage, `I`=Ice/Snow, `F`=Flooding, `L`=Closure, `O`=Other |
| `TRVLDRCTCD`         | string  | Travel direction: `EW` or `NS`                      |
| `TXDOTCOUNTYNBR`     | int     | TxDOT county number                                 |
| `FROMDISPMS`         | float   | Start milepost                                      |
| `TODISPMS`           | float   | End milepost                                        |
| `FROMRMKRNBR`        | string  | Start reference marker                              |
| `TORMKRNBR`          | string  | End reference marker                                |
| `CONDLMTFROMDSCR`    | string  | Human-readable start location description           |
| `CONDLMTTODSCR`      | string  | Human-readable end location description             |
| `CNSTRNTDETOURFLAG`  | Y/N     | Detour information available                        |
| `CNSTRNTDELAYFLAG`   | Y/N     | Motorist delays expected                            |
| `CNSTRNTMETROFLAG`   | Y/N     | Metro area condition                                |
| `lastUpdated`        | int     | Epoch milliseconds of last refresh                  |
| `sort`               | int     | Display sort order (higher = more severe)           |

---

### `futureConditionsPoint` / `futureConditionsLine` — ~296 records

Planned future road conditions.  Same schema as current conditions.

---

### `floodPoint`

Flood gauge sensor readings.  Fields include `RegionCode`, `StreamElevationLatestValue`,
`StreamElevationLatestTimestamp`, `PrecipitationLatestValue`, etc.  Returns 0 records
when no active flooding is detected.

---

### `contraflow_dissolve` — 10 records

Contraflow/evacuation route segments.  Field: `routeid`.

---

### `evaculanes` — 6 records

Evacuation lane assignments.  Field: `routeid`.

---

## Authentication

**No API key or login is required.**

The MapLarge API is publicly accessible.  The only requirement is that
requests include browser-style origin headers:

```
Origin:  https://drivetexas.org
Referer: https://drivetexas.org/
```

Without these headers the server returns HTTP 403.

The `aInfo=mluser:null;mltoken:null` parameter seen in some URLs is a legacy
format from an older MapLarge API path and is not required for `ProcessDirect`.

---

## Camera Stream URLs

Each camera provides multiple stream formats served by SkyVDN:

| Format | URL Pattern | Port | Protocol |
|--------|-------------|------|----------|
| HLS    | `https://s70.us-east-1.skyvdn.com:443/rtplive/<CAM_ID>/playlist.m3u8` | 443 | HTTPS |
| RTSP   | `rtsp://s70.us-east-1.skyvdn.com:554/rtplive/<CAM_ID>` | 554 | RTSP |
| RTMP   | `rtmp://s70.us-east-1.skyvdn.com:1935/rtplive/<CAM_ID>` | 1935 | RTMP |

**HLS playback examples:**

```bash
# VLC
vlc "https://s70.us-east-1.skyvdn.com:443/rtplive/TX_HOU_1002/playlist.m3u8"

# ffmpeg — save 30s clip
ffmpeg -i "https://s70.us-east-1.skyvdn.com:443/rtplive/TX_HOU_1002/playlist.m3u8" \
       -t 30 -c copy output.mp4

# ffmpeg — pipe to stdout
ffplay "https://s70.us-east-1.skyvdn.com:443/rtplive/TX_HOU_1002/playlist.m3u8"
```

**Note on `imageurl`:** The snapshot PNG URL in camera records uses
`https://localhost/thumbs/<CAM_ID>.flv.png`.  This is the internal URL as
stored in the MapLarge database.  The actual public thumbnail URL is not
exposed through this API; use the HLS stream or take a snapshot via ffmpeg.

---

## Quick Start

No installation required — uses only Python stdlib.

```python
from txdot_client import TxDOTClient

client = TxDOTClient()

# List cameras in Austin
cameras = client.get_cameras(jurisdiction="Austin", take=10)
for cam in cameras:
    print(f"{cam.name:20s} {cam.description:40s} {cam.hls_url}")

# Iterate over ALL cameras (handles pagination)
for cam in client.iter_cameras(active_only=True):
    print(cam.name, cam.hls_url)

# Get current road conditions
conditions = client.get_conditions(take=20)
for cond in conditions:
    print(f"{cond.route:10s} {cond.condition_type_label:15s} {cond.description[:60]}")

# Filter conditions by type
construction = client.get_conditions(condition_type="C", take=50)

# Future planned conditions
future = client.get_conditions(future=True, take=20)

# Site status
info = client.get_site_info()
print(f"Site working: {info.working}, last updated: {info.date_dt}")

# All districts
districts = client.get_jurisdictions()

# Raw API access for any table
result = client.raw_query("floodPoint", ["*"], take=10)
```

---

## CLI Reference

```
usage: txdot_client.py [-h] [--timeout SECS] COMMAND ...

Commands:
  cameras     List traffic cameras
  conditions  List road conditions
  info        Show DriveTexas site status
  stats       Show system-wide statistics
  stream      Get stream URL for a specific camera
```

### `cameras`

```
python txdot_client.py cameras [--jurisdiction CITY] [--route ROUTE]
                                [--active] [--take N] [--json]
```

Options:
- `--jurisdiction`, `-j` — Filter by TxDOT district city (e.g. `Houston`, `Dallas`)
- `--route`, `-r` — Filter by route name (e.g. `IH0035`)
- `--active` — Show only active cameras
- `--take N`, `-n N` — Maximum results (default: 20)
- `--json` — Output as JSON array

Examples:
```bash
python txdot_client.py cameras --jurisdiction Austin --take 20
python txdot_client.py cameras --route IH0035 --take 10
python txdot_client.py cameras --active --take 50 --json
```

### `conditions`

```
python txdot_client.py conditions [--route ROUTE] [--type TYPE]
                                   [--future] [--take N] [--json]
```

Options:
- `--route`, `-r` — Filter by route (e.g. `IH0035`)
- `--type`, `-t` — Filter by type code: `C`=construction, `A`=accident, `L`=closure, `D`=damage, `I`=ice/snow, `F`=flooding, `O`=other
- `--future`, `-f` — Show planned future conditions instead of current
- `--take N`, `-n N` — Maximum results (default: 20)
- `--json` — Output as JSON array

Examples:
```bash
python txdot_client.py conditions --take 30
python txdot_client.py conditions --type A --take 10
python txdot_client.py conditions --future --take 20
python txdot_client.py conditions --route IH0010 --json
```

### `info`

```
python txdot_client.py info [--json]
```

Displays DriveTexas site status, including the active splash screen message
and last configuration update date.

### `stats`

```
python txdot_client.py stats
```

Fetches camera counts by district and condition totals.
(Note: makes multiple API calls — may take 10–20 seconds.)

### `stream`

```
python txdot_client.py stream CAMERA_NAME [--json]
```

Look up all stream URLs for a specific camera by its ID.

Example:
```bash
python txdot_client.py stream TX_HOU_1002
python txdot_client.py stream TX_DAL_001 --json
```

---

## Python API Reference

### `TxDOTClient(timeout=30)`

Main client class.  `timeout` sets the default HTTP request timeout in seconds.

---

#### `get_cameras(...) -> List[Camera]`

```python
client.get_cameras(
    jurisdiction=None,   # str: "Houston", "Dallas", "Austin", ...
    route=None,          # str: "IH0035", "US0290", "FM1709", ...
    active_only=False,   # bool: exclude offline cameras
    take=500,            # int: max results
    start=0,             # int: pagination offset (after client filtering)
)
```

Returns a list of `Camera` objects.  Filtering is applied client-side.

---

#### `iter_cameras(...) -> Iterator[Camera]`

Same parameters as `get_cameras` except `take`/`start` are replaced by:
- `page_size=500` — API page size

Yields `Camera` objects while handling pagination transparently.
Use this for large result sets (e.g. all Houston cameras).

---

#### `get_camera_count(...) -> int`

Returns the count of cameras matching the given filters.

---

#### `get_jurisdictions() -> List[str]`

Returns a sorted list of all TxDOT district names.

---

#### `get_conditions(...) -> List[RoadCondition]`

```python
client.get_conditions(
    route=None,           # str: "IH0035"
    condition_type=None,  # str: "C", "A", "D", "I", "F", "L", "O"
    future=False,         # bool: query future conditions table
    take=500,
    start=0,
)
```

---

#### `iter_conditions(...) -> Iterator[RoadCondition]`

Same as `get_conditions` with pagination, yields `RoadCondition` objects.

---

#### `get_site_info() -> SiteInfo`

Fetches site configuration from GCS.

---

#### `raw_query(table, fields, *, take=100, start=0) -> dict`

Direct access to any MapLarge table.  Returns the raw API response dict.

```python
result = client.raw_query("floodPoint", ["*"], take=10)
rows = result["data"]["data"]  # columnar arrays
total = result["data"]["totals"]["Records"]
```

---

### `Camera` Dataclass

| Attribute       | Type    | Description                              |
|-----------------|---------|------------------------------------------|
| `name`          | str     | Camera ID, e.g. `TX_HOU_1002`            |
| `description`   | str     | Location label                           |
| `jurisdiction`  | str     | TxDOT district city                      |
| `route`         | str     | Primary route name                       |
| `direction`     | str     | Travel direction                         |
| `mrm`           | float   | Milepost reference marker                |
| `active`        | int     | 1=active, 0=offline                      |
| `problem_stream`| int     | Non-zero = known stream problem          |
| `last_updated`  | int     | Epoch milliseconds of last refresh       |
| `camera_id`     | int     | Internal numeric ID                      |
| `image_url`     | str     | Snapshot URL (contains `localhost`)      |
| `hls_url`       | str     | HLS m3u8 stream URL                      |
| `ios_url`       | str     | iOS HLS URL (same as `hls_url`)          |
| `rtsp_url`      | str     | RTSP stream URL                          |
| `rtmp_url`      | str     | RTMP stream URL                          |
| `clsps_url`     | str     | SkyVDN CLSPS URL                         |
| `preroll_url`   | str     | HLS pre-roll URL                         |
| `device_id`     | int     | Hardware device ID                       |
| `distance`      | str     | Distance annotation                      |
| `is_active`     | bool    | Property: active and no stream problem   |
| `last_updated_dt`| datetime\|None | `last_updated` as UTC datetime  |

---

### `RoadCondition` Dataclass

| Attribute         | Type    | Description                              |
|-------------------|---------|------------------------------------------|
| `condition_id`    | str     | HCRS condition ID                        |
| `route`           | str     | Route name, e.g. `IH0035`               |
| `roadway_name`    | str     | Roadway name                             |
| `description`     | str     | Narrative text (may contain HTML)        |
| `start_ts`        | int     | Start time (epoch ms)                    |
| `end_ts`          | int     | End time (epoch ms, 0=no end)            |
| `condition_type`  | str     | Type code (`C`, `A`, `D`, etc.)          |
| `travel_direction`| str     | `EW` or `NS`                             |
| `county_nbr`      | int     | TxDOT county number                      |
| `from_milepost`   | float   | Start milepost                           |
| `to_milepost`     | float   | End milepost                             |
| `from_marker`     | str     | Start reference marker                   |
| `to_marker`       | str     | End reference marker                     |
| `from_description`| str     | Start location text                      |
| `to_description`  | str     | End location text                        |
| `detour_flag`     | int     | Non-zero if detour available             |
| `delay_flag`      | int     | Non-zero if delays expected              |
| `metro_flag`      | int     | Non-zero if metro area                   |
| `last_updated`    | int     | Epoch ms of last refresh                 |
| `sort_order`      | int     | Display sort order                       |
| `condition_type_label` | str | Human-readable type (e.g. `Construction`) |
| `start_dt`        | datetime\|None | Start time as UTC datetime       |
| `end_dt`          | datetime\|None | End time as UTC datetime         |
| `expects_delays`  | bool    | Property: True if delays expected        |

---

### `SiteInfo` Dataclass

| Attribute      | Type      | Description                              |
|----------------|-----------|------------------------------------------|
| `working`      | bool      | Site is operational                      |
| `splash_screen`| str       | Current splash/alert message             |
| `showing`      | int       | Display mode (3 = normal)                |
| `deactivated`  | List[str] | Deactivated feature IDs                  |
| `date`         | int       | Config publish date (epoch ms)           |
| `modal`        | bool      | Show modal notice                        |
| `redirect`     | str\|None | Redirect instruction if set              |
| `date_dt`      | datetime\|None | Config date as UTC datetime        |

---

## Pagination

The MapLarge API returns up to **500 records per call**.  The total record
count is always returned in `data.totals.Records`.

The client handles pagination automatically in all `iter_*` methods.
For `get_*` methods without filters, a single page is fetched.  For filtered
results, the client pages through all records and collects matching ones.

Example — iterate all 3,410 cameras efficiently:

```python
client = TxDOTClient()

# Fetches 7 pages of 500 records each
for cam in client.iter_cameras():
    process(cam)

# All Houston cameras (859) — still pages through all 3410 to filter
for cam in client.iter_cameras(jurisdiction="Houston"):
    process(cam)
```

---

## Known Limitations

1. **Server-side filtering not supported**: The public API endpoint returns
   HTTP 500 for any `where` clause.  All filtering is done client-side, which
   means fetching all records to filter by district/route.

2. **Image snapshots unavailable**: The `imageurl` field contains an internal
   `https://localhost/thumbs/<CAM_ID>.flv.png` URL that is only accessible
   from inside the TxDOT network.  Use ffmpeg to capture frames from the HLS
   stream instead.

3. **SkyVDN stream accessibility**: Some streams may require network access to
   `s70.us-east-1.skyvdn.com` on port 443.  In restricted network environments
   (firewalled corporate networks), RTSP (port 554) or RTMP (port 1935) streams
   may not be reachable.

4. **No geospatial coordinates in basic query**: Latitude/longitude values are
   stored in the map tile system and UTFGrid, not returned in basic table queries.
   Point geometry is accessible through the `line` field but requires additional
   parsing of the WKT format returned by MapLarge.

5. **Rate limiting**: No rate limiting was observed, but be respectful with
   request frequency.  Cache results where possible.  The data refreshes
   approximately every 30 seconds.

---

## Legal Notes

This client accesses publicly available data served by TxDOT through
DriveTexas.org.  Per the site's disclaimer:

> *TxDOT is committed to your safety and to the reliability of the information
> contained on this site.  Road conditions can change quickly, and we encourage
> drivers to exercise caution.*

- Use this data responsibly and in compliance with [TxDOT's privacy policy](https://www.txdot.gov/about/privacy-policy.html).
- Do not use this data to make automated driving decisions.
- Do not build applications that overwhelm TxDOT's infrastructure with excessive requests.
- The Google Maps API key embedded in the DriveTexas bundle is restricted to the `drivetexas.org` origin and cannot be used from other domains.

---

*Reverse-engineered 2026-03-27 from `https://drivetexas.org`. Data belongs to TxDOT.*
