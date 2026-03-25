# World Weather Online — Reverse-Engineered API Client

## Overview

This document describes the internal and public APIs of
[worldweatheronline.com](https://www.worldweatheronline.com) as discovered
through network traffic analysis, JavaScript source review, and HTML
inspection of the site.

Two tiers of API exist:

| Tier | Base URL | Auth | Data format |
|------|----------|------|-------------|
| **Internal (scraper)** | `https://www.worldweatheronline.com` | None (session cookie) | HTML fragment (JSON envelope) |
| **Premium REST** | `https://api.worldweatheronline.com/premium/v1` | `?key=<API_KEY>` | JSON / XML / CSV / TAB |

---

## Infrastructure

```
Website CDN:   https://cdn.worldweatheronline.com/
Website:       https://www.worldweatheronline.com/
Premium API:   https://api.worldweatheronline.com/premium/v1/
```

The website is an **ASP.NET application** served via BunnyCDN. JavaScript
files are versioned at `/staticv150817/assets-202110/js/`.

A **service worker** (`/wwo_sw_v326.min.js`) caches dynamic `.aspx` pages
(excluding `/hwd/` and `/weather-api/` pages) for offline use.

---

## 1. Internal AJAX Endpoints

These endpoints follow the ASP.NET `PageMethods` / WebMethod pattern:

```
POST <page-url>/<MethodName>
Content-Type: application/json; charset=utf-8
Content-Encoding: gzip
Body: { 'd': '<encoded-data-string>' }
```

All responses are JSON objects with a single `"d"` key containing an
**HTML fragment** string.

### 1.1 Forecast Endpoints

#### `POST /v2/weather.aspx/load_calendar`

Returns a 14-day daily weather summary (calendar view).

**Body:**
```json
{ "d": "2026-03-25:68547:London, United Kingdom:0:en:False:1:1:2:1:1:www.worldweatheronline.com/london-weather/city-of-london-greater-london/gb.aspx" }
```

**`d` field format (colon-separated):**
```
date       : YYYY-MM-DD
areaid     : integer (internal area identifier)
name       : location display name
tz_offset  : integer timezone offset in hours (negative for west of UTC)
lang       : language code (e.g. "en")
bool_flag  : "False" or "True"
t          : temperature unit (1=°C, 2=°F)
p          : precipitation unit (1=mm, 2=inches)
ps         : pressure unit (1=mb, 2=inches)
w          : wind speed unit (1=km/h, 2=mph, 3=knots, 4=beaufort, 5=m/s)
v          : visibility unit (1=km, 2=miles)
page_url   : full URL of the current page (without https://)
```

**Response HTML structure:**
```html
<table>
  <tr>
    <td>Date | High | Low | Wind | Cloud | Rain | Pressure | Humidity | Sunrise | Sunset</td>
    <!-- one row per day for 14 days -->
  </tr>
</table>
```

---

#### `POST /v2/weather.aspx/load_wxdn`

Returns a short-term breakdown by Morning / Afternoon / Evening / Overnight.

**Body:** Same format as `load_calendar` (uses `hd14dayfx` field).

---

#### `POST /v2/weather.aspx/loaduvindex`

Returns UV index values for upcoming days.

**Body format (@ separator):**
```
datetime@areaid@name@tz_offset@lang@bool@t@p@ps@w@v@lat@lon
```
Example:
```json
{ "d": "2026-03-25 02:32:53@68547@London@0@en@False@1@1@2@1@1@51.517@-0.106" }
```

---

### 1.2 Search Endpoints

#### `POST /search-weather.aspx/load_search`

Location and sports venue search.

**Body:**
```json
{ "query": "London" }
```

**Response:** HTML fragment containing matched results including:
- City/town weather links
- Cricket ground weather links
- Football stadium weather links
- Golf course weather links

---

#### `POST /v2/root.aspx/Search`

Area/root-level city search (scoped to root-level areas).

**Body:**
```json
{ "st": "London", "id": "0" }
```

---

#### `POST /v2/region.aspx/Search`

Region-scoped city search.

**Body:**
```json
{ "st": "London", "id": "<region_id>" }
```

---

### 1.3 Other Endpoints

#### `POST /Default.aspx/load_hp_sports`

Homepage sports weather widget (no body required).

**Body:** `{}`

---

#### `POST /v2/change-units.aspx/UpdateUnits`

Update user display unit preferences (sets server-side cookie).

**Body:**
```json
{ "t": 1, "p": 1, "ps": 1, "w": 1, "v": 1 }
```

Unit values:
- `t` (temperature): 1=°C, 2=°F
- `p` (precipitation): 1=mm, 2=inches
- `ps` (pressure): 1=mb, 2=inches
- `w` (wind): 1=km/h, 2=mph, 3=knots, 4=Beaufort, 5=m/s
- `v` (visibility): 1=km, 2=miles

---

#### `POST /v2/favourites.aspx/DeleteFav`

Delete a saved favourite location (requires authenticated session).

**Body:**
```json
{ "hdwc1": "<location_id>" }
```

---

## 2. Page-Based (GET) Endpoints

These return full HTML pages. Extract the `<input type="hidden">` fields to
build the AJAX endpoint payloads.

### 2.1 Current & Forecast Weather

```
GET https://www.worldweatheronline.com/v2/weather.aspx?q=<location>
GET https://www.worldweatheronline.com/<city>-weather/<region>/<cc>.aspx
```

**Parameters:**
- `q` — location query (city name, "lat,lon", UK postcode, US zip code)
- `tp` — time period for hourly: 1, 3, 6, 12 (optional)
- `day` — number of days ahead for hourly pages (e.g. `day=20`)

**Key hidden fields:**

| Field ID | Example value | Description |
|----------|---------------|-------------|
| `ctl00_MainContentHolder_hd14dayfx` | `2026-03-25:68547:London, United Kingdom:0:en:False:1:1:2:1:1:www...` | Used for AJAX forecast calls |
| `ctl00_MainContentHolder_hdcurrentwx` | `2026-03-25 02:32:53@68547@London@0@en@False@1@1@2@1@1@51.517@-0.106` | Used for current wx / UV calls |
| `ctl00_MainContentHolder_hdchartdata` | `2026-03-25:68547:London, United Kingdom:LOCAL_WEATHER:1` | Chart data source |
| `ctl00_hdlat` | `51.517` | Latitude |
| `ctl00_hdlon` | `-0.106` | Longitude |
| `ctl00_areaid` | `68547` | Internal location ID |

**Weather type codes** (in `hdchartdata` 4th field):
- `LOCAL_WEATHER` — standard city/town weather
- `CRICKET` — cricket ground weather
- `SKI` — ski/mountain weather

**Sport type** (in `hd14dayfx` 4th field):
- `0` — standard city/town weather
- `1` — ski resort weather

---

### 2.2 Hourly Weather Page

```
GET https://www.worldweatheronline.com/<city>-weather/<region>/<cc>.aspx?day=20&tp=1
GET https://www.worldweatheronline.com/<city>-weather/<region>/<cc>.aspx?day=20&tp=1#<YYYYMMDD>
```

Returns an HTML table per day with columns: `Time | Weather | Temp | Rain | Cloud | Pressure | Wind | Gust | Dir`

---

### 2.3 Historical Weather Page

```
GET  https://www.worldweatheronline.com/<city>-weather-history/<region>/<cc>.aspx
POST https://www.worldweatheronline.com/<city>-weather-history/<region>/<cc>.aspx
```

The POST form submission requires:

| Form field | Value |
|------------|-------|
| `__VIEWSTATE` | From hidden input in GET response |
| `__VIEWSTATEGENERATOR` | From hidden input |
| `ctl00$MainContentHolder$txtPastDate` | `YYYY-MM-DD` |
| `ctl00$MainContentHolder$butShowPastWeather` | `Get Weather` |

Historical data is available from **2008-07-01** to present.

---

### 2.4 Ski Weather Page

```
GET https://www.worldweatheronline.com/ski-weather/<region>/<cc>.aspx
```

Uses the same hidden fields as local weather but with `hd14dayfx` 4th field set to `1` (sport type = ski).

---

### 2.5 Sports Venue Weather Pages

```
GET https://www.worldweatheronline.com/cricket/<venue>-weather/<cc>.aspx
GET https://www.worldweatheronline.com/golf/<venue>-weather/<cc>.aspx
GET https://www.worldweatheronline.com/football/<venue>-weather/<cc>.aspx
```

---

## 3. Premium REST API

**Base URL:** `https://api.worldweatheronline.com/premium/v1/`

**Authentication:** `?key=<YOUR_API_KEY>` on every request

Sign up for a free 30-day trial at:
https://www.worldweatheronline.com/weather-api/signup.aspx

All endpoints use **HTTP GET** and return **JSON** (default), XML, CSV, or TAB.

Common parameters for all endpoints:
- `key` — your API key (required)
- `format` — `json` (default), `xml`, `csv`, `tab`

---

### 3.1 `GET /premium/v1/weather.ashx` — Forecast

**Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `q` | string | required | Location (city name, lat/lon, postcode, IP) |
| `num_of_days` | int | 1 | Forecast days (1–14) |
| `tp` | int | — | Hourly interval: 1, 3, 6, 12, or 24 |
| `fx` | int | 1 | Include forecast (0/1) |
| `cc` | int | 1 | Include current conditions (0/1) |
| `mca` | int | 0 | Include monthly climate averages (0/1) |
| `fx24` | int | 0 | Include 24h wind gust forecast (0/1) |
| `includelocation` | int | 0 | Include location object (0/1) |
| `showComments` | int | 0 | Include text descriptions (0/1) |
| `lang` | string | en | Response language code |

**Example:**
```
GET https://api.worldweatheronline.com/premium/v1/weather.ashx
    ?key=YOUR_KEY&q=London&num_of_days=3&tp=3&format=json
```

---

### 3.2 `GET /premium/v1/past-weather.ashx` — Historical

**Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `q` | string | required | Location |
| `date` | string | required | Start date `YYYY-MM-DD` (min: 2008-07-01) |
| `enddate` | string | — | End date (inclusive) |
| `tp` | int | — | Hourly interval: 1, 3, 6, 12, or 24 |
| `includelocation` | int | 0 | Include location object |

**Example:**
```
GET https://api.worldweatheronline.com/premium/v1/past-weather.ashx
    ?key=YOUR_KEY&q=London&date=2024-06-15&tp=3&format=json
```

---

### 3.3 `GET /premium/v1/marine.ashx` — Marine Weather

**Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `q` | string | required | `"lat,lon"` coordinates |
| `tp` | int | — | Hourly interval: 1, 3, 6, 12, or 24 |
| `tide` | int | 0 | Include tide data (0/1) |

**Unique marine data fields:**
- Significant wave height (m)
- Swell height (m)
- Swell period (s)
- Swell direction
- Sea/water temperature (°C)
- Tide data (time, height, type)

**Example:**
```
GET https://api.worldweatheronline.com/premium/v1/marine.ashx
    ?key=YOUR_KEY&q=51.5,1.5&tp=3&tide=1&format=json
```

---

### 3.4 `GET /premium/v1/ski.ashx` — Ski/Mountain Weather

**Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `q` | string | required | Resort name or `"lat,lon"` |
| `num_of_days` | int | 1 | Days (1–7) |
| `tp` | int | — | Hourly interval |

**Unique ski data fields:**
- Top/middle/bottom elevation forecasts
- Snow depth (cm)
- Snow chance (%)
- Wind chill temperatures

**Example:**
```
GET https://api.worldweatheronline.com/premium/v1/ski.ashx
    ?key=YOUR_KEY&q=Chamonix&num_of_days=5&format=json
```

---

### 3.5 `GET /premium/v1/search.ashx` — Location Search

**Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `q` | string | required | Search string |
| `num_of_results` | int | 10 | Max results (1–200) |
| `timezone` | int | 1 | Include timezone (0/1) |

Returns: area name, country, region, latitude, longitude, population, timezone.

---

### 3.6 `GET /premium/v1/tz.ashx` — Time Zone

**Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `q` | string | Location query |

Returns: local time, UTC offset (hours and minutes), timezone name.

---

### 3.7 `GET /premium/v1/astronomy.ashx` — Astronomy Data

**Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `q` | string | Location query |
| `date` | string | Date `YYYY-MM-DD` |

Returns: sunrise, sunset, moonrise, moonset, moon illumination, moon phase.

---

## 4. URL Patterns

### Weather Page URL Structure
```
/v2/weather.aspx?q=<query>                    — Dynamic (works for any query)
/<city>-weather/<region>/<cc>.aspx            — Canonical city page
/<city>-weather/<region>/<cc>.aspx?tp=1&day=20 — Hourly view
```

### Historical Page URL Structure
```
/<city>-weather-history/<region>/<cc>.aspx    — Historical data page
```

### Ski Page URL Structure
```
/<resort>-ski-weather/<region>/<cc>.aspx      — Ski resort page
/ski-weather/<region>/<cc>.aspx               — Regional ski page
```

### Sports Venue URL Structure
```
/cricket/<venue>-weather/<cc>.aspx
/golf/<venue>-weather/<cc>.aspx
/football/<venue>-weather/<cc>.aspx
```

### Search URL
```
/search-weather.aspx?q=<query>
```

---

## 5. Weather Icon URLs

Weather condition icons are hosted on CDN:

```
https://cdn.worldweatheronline.com/images/weather/small/<code>_day_sm.png
https://cdn.worldweatheronline.com/images/weather/small/<code>_night_sm.png
https://cdn.worldweatheronline.com/images/weather/large/<code>_day_lg.png
https://cdn.worldweatheronline.com/images/weather/large/<code>_night_lg.png
```

Common condition codes: 113 (Sunny), 116 (Partly Cloudy), 119 (Cloudy),
122 (Overcast), 143 (Mist), 176 (Patchy Rain), 179 (Patchy Snow),
182 (Patchy sleet), 185 (Patchy freezing drizzle), 200 (Thunder),
227 (Blowing snow), 230 (Blizzard), 248 (Fog), 260 (Freezing fog),
263 (Light drizzle), 266 (Light drizzle), 281 (Freezing drizzle),
284 (Heavy freezing drizzle), 293-308 (Light to heavy rain),
311-314 (Light to moderate freezing rain), 317-320 (Light to moderate sleet),
323-338 (Light to heavy snow), 350 (Ice pellets), 353-359 (Rain/drizzle),
362-371 (Light to moderate sleet/snow), 374-377 (Light to moderate ice pellets),
386-395 (Thundery rain/snow).

---

## 6. Authentication & Session

### Session Cookies

Set by the homepage on first visit:

| Cookie | Description |
|--------|-------------|
| `wwoanon` | Anonymous session identifier (long-lived, expires 2028) |
| `WWOZMHSession` | Short-term session token |
| `wwowebsst` | Web session security token |

### API Key

Premium API key must be included as `?key=<YOUR_KEY>` on every REST API call.

Register at: https://www.worldweatheronline.com/weather-api/signup.aspx

---

## 7. Quick Start

### Installation

```bash
pip install requests
```

### Usage (no API key — scraper mode)

```python
from worldweatheronline_client import WorldWeatherOnlineClient

client = WorldWeatherOnlineClient()

# Search for locations
urls = client.search("Tokyo")
print(urls[:3])

# Get 14-day forecast
forecast = client.get_forecast("Tokyo")
print(forecast["calendar_text"])

# Hourly weather
hourly = client.get_hourly("Tokyo")
for table in hourly["tables"][:2]:
    print(table[:200])

# Historical weather (London, 2024-06-15)
history = client.get_historical(
    "https://www.worldweatheronline.com/"
    "london-weather-history/city-of-london-greater-london/gb.aspx",
    "2024-06-15",
)
print(history["history_text"][:500])

# Ski weather
ski = client.get_ski_forecast(
    "https://www.worldweatheronline.com/ski-weather/akershus/no.aspx"
)
print(ski["short_term_text"][:400])

# Marine weather (coordinates)
marine = client.get_marine_forecast(50.9, -1.4)
print(marine["calendar_text"][:300])
```

### Usage (with premium API key)

```python
from worldweatheronline_client import WorldWeatherOnlineClient

client = WorldWeatherOnlineClient(api_key="YOUR_API_KEY")

# Current + 5-day forecast with hourly (3h intervals)
data = client.api_forecast("London", num_of_days=5, tp=3)

# Historical weather
data = client.api_historical("New York", "2024-07-04", tp=3)

# Marine weather
data = client.api_marine("51.5,1.5", tp=3, tide=1)

# Ski weather
data = client.api_ski("Chamonix", num_of_days=7)

# Location search
data = client.api_search("Lon", num_of_results=20)

# Time zone
data = client.api_timezone("Sydney")

# Astronomy
data = client.api_astronomy("London", "2024-12-21")
```

### Run the demo

```bash
# Scraper demo (no key):
python worldweatheronline_client.py

# Premium API demo (with key):
python worldweatheronline_client.py YOUR_API_KEY
```

---

## 8. Notes & Limitations

1. **Rate limiting:** Be polite. The client adds a 0.5s delay between
   requests by default (`request_delay` constructor parameter).

2. **VIEWSTATE:** Historical weather forms require a fresh `__VIEWSTATE`
   token extracted from the GET response. These are ephemeral.

3. **Units:** The scraper endpoints return data in whatever unit the
   server-side cookie is set to. Call `client._sess.set_units()` to change
   units before making requests.

4. **Sports type flag:** The `hd14dayfx` hidden field 4th token distinguishes
   weather type: `0` = standard city, `1` = ski resort.

5. **Area IDs:** WWO uses internal integer area IDs (visible in hidden fields
   as `ctl00_areaid`). These are stable identifiers for locations.

6. **Premium API minimum date:** Historical data starts from `2008-07-01`.

7. **No official SLA:** The scraper endpoints are internal and may change
   without notice. The premium REST API is stable and documented.
