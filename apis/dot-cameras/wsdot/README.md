# WSDOT Camera & Traffic API Client

Comprehensive Python client for the Washington State Department of Transportation
(WSDOT) public camera system, traffic data APIs, ferry services, and work zone feeds.
Reverse-engineered from live network traffic and official WSDOT API documentation.

---

## Table of Contents

1. [Overview](#overview)
2. [Authentication](#authentication)
3. [Quick Start](#quick-start)
4. [Cameras](#cameras)
5. [Mountain Pass Conditions](#mountain-pass-conditions)
6. [Traffic Flow](#traffic-flow)
7. [Travel Times](#travel-times)
8. [Highway Alerts](#highway-alerts)
9. [Weather Stations](#weather-stations)
10. [Washington State Ferries](#washington-state-ferries)
11. [Work Zones (WZDx)](#work-zones-wzdx)
12. [All Discovered Endpoints](#all-discovered-endpoints)
13. [Data Formats](#data-formats)
14. [Region & Route Codes](#region--route-codes)

---

## Overview

WSDOT exposes its traffic and camera data through three layers:

| Layer | Auth | Format | Coverage |
|-------|------|--------|----------|
| Public RSS feeds | None | RSS/XML | Cameras, passes, flow, travel times, alerts, weather |
| Public KML feeds | None | KML/XML | Camera GPS coordinates |
| Public GeoJSON (WZDx) | None | GeoJSON v4.2 | Work zones, field devices |
| REST JSON/XML APIs | AccessCode | JSON | Full data, all 13 services |
| SOAP/WSDL APIs | AccessCode | XML | Same 13 services via SOAP |
| WSF Ferries API | Optional | JSON | Vessel locations, schedules, terminals |

---

## Authentication

### WSDOT Traveler Information API (AccessCode)

Free registration at: https://www.wsdot.wa.gov/Traffic/api/

- Register with email address
- Receive an `AccessCode` (UUID format, e.g. `xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx`)
- Pass as query parameter: `?AccessCode={your_code}`
- No rate limits documented; reasonable use expected
- AccessCode required for all 13 REST/SOAP services

### Washington State Ferries API (apiaccesscode)

Optional access code available at: https://www.wsdot.wa.gov/ferries/api/

- Basic vessel locations and terminal info work **without** an access code
- Schedule data and details may require `apiaccesscode` query parameter
- More detailed real-time data available with registration

### Public Endpoints (no auth)

The following work without any authentication:
- All RSS feeds (`rss.aspx`)
- All KML feeds (`kml.aspx`)
- Camera images CDN (`images.wsdot.wa.gov`)
- WZDx GeoJSON feeds (`wzdx.wsdot.wa.gov`)
- Basic WSF vessel and terminal data

---

## Quick Start

```python
from wsdot_cams_client import (
    WSDOTCameraClient,
    fetch_highway_alerts_rss,
    fetch_mountain_pass_conditions,
    get_ferry_vessel_locations,
    fetch_work_zones,
    WSDOT_ENDPOINTS,
)

# No auth required - public feeds
client = WSDOTCameraClient()

# Get all cameras (public RSS feed, ~1600+ cameras)
cameras = client.get_all_cameras_public()
print(f"Total cameras: {len(cameras)}")

# Get Snoqualmie Pass cameras
snoq = client.get_snoqualmie_pass_cameras()
for cam in snoq:
    print(f"{cam.title}: {cam.image_url}")

# Mountain pass conditions (RSS, no auth)
passes = fetch_mountain_pass_conditions()
for p in passes:
    print(f"{p.mountain_pass_name}: {p.road_condition}")

# Active highway alerts
alerts = fetch_highway_alerts_rss()
print(f"Active alerts: {len(alerts)}")

# Ferry vessel locations
vessels = get_ferry_vessel_locations()
print(f"WSF vessels reporting: {len(vessels)}")

# Work zones
zones = fetch_work_zones()
print(f"Work zones: {len(zones)}")

# With AccessCode (replace with your code)
ACCESS_CODE = "your-access-code-here"
all_cameras = client.get_all_cameras(access_code=ACCESS_CODE)
passes_auth = fetch_mountain_pass_conditions(access_code=ACCESS_CODE)
```

---

## Cameras

### Image URL Pattern

```
https://images.wsdot.wa.gov/{region}/{route3digit}vc{milepost5digit}.jpg
```

Examples:
```
https://images.wsdot.wa.gov/sc/090vc05200.jpg   # I-90 MP 52.0 (Snoqualmie area)
https://images.wsdot.wa.gov/nw/005vc16842.jpg   # I-5 MP 168.42 (Seattle)
https://images.wsdot.wa.gov/er/090vc27000.jpg   # I-90 MP 270.0 (Eastern WA)
```

- Route number: zero-padded to 3 digits (`090` for I-90)
- Milepost: hundredths precision, zero-padded to 5 digits (`05200` for MP 52.00)
- Images are JPEG, typically 320x240 or 640x480
- No authentication required
- Refreshed approximately every 1-2 minutes

### Public Feed (No Auth)

```python
# Get all cameras from RSS feed (returns ~1600 Camera objects)
cameras = client.get_all_cameras_public()

# Filter by region
nw_cameras = [c for c in cameras if c.region == "NW"]

# Search cameras by title keyword
i5_cams = client.search_cameras_public(title_contains="I-5")

# Get KML feed (includes GPS coordinates)
kml_cameras = client.get_all_cameras_kml()
```

### Authenticated REST API

```python
# Full camera data including direction, owner, state route
cameras = client.get_all_cameras(access_code=ACCESS_CODE)

# Search by route and/or region
sr2_cams = client.search_cameras(
    access_code=ACCESS_CODE,
    state_route="002",       # US-2 (Stevens Pass)
    region="NC",             # North Central
)

# Single camera by ID
cam = client.get_camera(access_code=ACCESS_CODE, camera_id=9920)
```

### Camera Dataclass

```python
@dataclass
class Camera:
    camera_id: int          # WSDOT internal ID
    title: str              # Human-readable name
    image_url: str          # Direct JPEG URL
    region: str             # Two-letter region code
    display_latitude: float
    display_longitude: float
    location: CameraLocation  # RoadName, MilePost, Direction, etc.
    last_updated: str
```

### Mountain Pass Camera Groups

```python
client.get_snoqualmie_pass_cameras()    # I-90, MP 46-62
client.get_stevens_pass_cameras()       # US-2, MP 58-70
client.get_white_pass_cameras()         # US-12
```

### Export

```python
# GeoJSON FeatureCollection
geojson = client.cameras_to_geojson(cameras)

# CSV string
csv_data = client.cameras_to_csv(cameras)

# Build image URL manually
url = client.build_image_url(region="sc", route_number=90, milepost=52.0)
# -> https://images.wsdot.wa.gov/sc/090vc05200.jpg
```

---

## Mountain Pass Conditions

### Endpoints

| Type | URL | Auth |
|------|-----|------|
| REST JSON | `https://www.wsdot.wa.gov/Traffic/api/MountainPassConditions/MountainPassConditionsREST.svc/GetMountainPassConditionsAsJson?AccessCode={code}` | AccessCode |
| Single pass | `.../GetMountainPassConditionAsJson?AccessCode={code}&PassConditionID={id}` | AccessCode |
| RSS feed | `https://www.wsdot.wa.gov/Traffic/api/MountainPassConditions/rss.aspx` | None |

### Usage

```python
# No auth (RSS)
passes = fetch_mountain_pass_conditions()

# With AccessCode (more detailed)
passes = fetch_mountain_pass_conditions(access_code=ACCESS_CODE)

# Single pass by ID
snoq = fetch_mountain_pass_conditions(access_code=ACCESS_CODE, pass_id=1)

# Active closures/advisories only
closed = get_active_pass_closures(access_code=ACCESS_CODE)
```

### Pass IDs

| ID | Pass Name | Route | Elevation |
|----|-----------|-------|-----------|
| 1 | Snoqualmie Pass | I-90 | 3,022 ft |
| 2 | Stevens Pass | US-2 | 4,061 ft |
| 3 | White Pass | US-12 | 4,500 ft |
| 4 | Blewett Pass | US-97 | 4,102 ft |
| 5 | Sherman Pass | SR-20 | 5,575 ft |
| 6 | Loup Loup Pass | SR-20 | 4,020 ft |
| 7 | Cayuse Pass | SR-410 | 4,694 ft |
| 8 | Chinook Pass | SR-410 | 5,430 ft |
| 9 | North Cascades (US-20) | SR-20 | 5,477 ft |

### MountainPassReport Fields

```python
@dataclass
class MountainPassReport:
    mountain_pass_id: int
    mountain_pass_name: str
    weather_condition: str    # "Overcast", "Snow", "Clear", etc.
    road_condition: str       # "Wet", "Snow covered", "Dry", etc.
    temperature: float        # Fahrenheit (air temp at pass)
    elevation: int            # feet
    travel_advisory_active: bool
    seasonal_closure: bool    # Pass closed for winter season
    restriction_one: str      # "Chains required on all vehicles"
    restriction_two: str      # "Chains or traction tires required"
    traction_advisory: bool
    date_updated: str         # ISO 8601
    forecast: str
    latitude: float
    longitude: float
```

---

## Traffic Flow

### Endpoints

| Type | URL | Auth |
|------|-----|------|
| REST JSON | `https://www.wsdot.wa.gov/Traffic/api/TrafficFlow/TrafficFlowREST.svc/GetTrafficFlowsAsJson?AccessCode={code}` | AccessCode |
| By route | `...?AccessCode={code}&StateRoute={sr}` | AccessCode |
| By region | `...?AccessCode={code}&Region={region}` | AccessCode |
| RSS feed | `https://www.wsdot.wa.gov/Traffic/api/TrafficFlow/rss.aspx` | None |

### Usage

```python
# Public RSS (limited data)
readings = fetch_traffic_flow_rss(highway="005")   # I-5

# Authenticated REST
readings = get_traffic_flow(
    access_code=ACCESS_CODE,
    state_route="005",    # I-5
    region_code="NW",     # Northwest region
)

# Find congested stations
congested = [r for r in readings if r.speed < 35]
```

### FlowReading Fields

```python
@dataclass
class FlowReading:
    flow_station_id: str    # e.g. "110ES53240"
    region: str
    station_name: str
    highway: str
    milepost: float
    direction: str          # "N", "S", "E", "W"
    lane_count: int
    occupancy: float        # percentage
    speed: float            # mph average
    flow_reading_value: float  # vehicles per hour
    time_updated: str       # ISO 8601
    latitude: float
    longitude: float
```

---

## Travel Times

### Endpoints

| Type | URL | Auth |
|------|-----|------|
| REST JSON (all) | `https://www.wsdot.wa.gov/Traffic/api/TravelTimes/TravelTimesREST.svc/GetTravelTimesAsJson?AccessCode={code}` | AccessCode |
| Single route | `.../GetTravelTimeAsJson?AccessCode={code}&TravelTimeID={id}` | AccessCode |
| RSS feed | `https://www.wsdot.wa.gov/Traffic/api/TravelTimes/rss.aspx` | None |

### Usage

```python
# Public RSS (~163 routes)
routes = fetch_travel_times_rss()
delayed = [r for r in routes if r.delay_minutes > 5]

# Authenticated REST
routes = get_travel_times(access_code=ACCESS_CODE)
route = get_travel_times(access_code=ACCESS_CODE, travel_time_id=123)
```

### TravelTimeRoute Fields

```python
@dataclass
class TravelTimeRoute:
    travel_time_id: int
    name: str               # e.g. "Everett-Seattle HOV"
    description: str
    average_time: int       # minutes (historical baseline)
    current_time: int       # minutes (current conditions)
    distance: float         # miles
    time_updated: str
    start_point_name: str
    end_point_name: str
    start_latitude: float
    start_longitude: float
    end_latitude: float
    end_longitude: float

    @property
    def delay_minutes(self) -> int: ...  # current - average (min 0)
```

---

## Highway Alerts

### Endpoints

| Type | URL | Auth |
|------|-----|------|
| REST (all) | `https://www.wsdot.wa.gov/Traffic/api/HighwayAlerts/HighwayAlertsREST.svc/GetAlertsAsJson?AccessCode={code}` | AccessCode |
| Single alert | `.../GetAlertAsJson?AccessCode={code}&AlertID={id}` | AccessCode |
| RSS feed | `https://www.wsdot.wa.gov/Traffic/api/HighwayAlerts/rss.aspx` | None |

Optional RSS/REST filters: `StateRoute`, `Region`, `County`, `StartSeverity`

### Usage

```python
# Public RSS feed (~100+ active alerts)
alerts = fetch_highway_alerts_rss()
alerts = fetch_highway_alerts_rss(state_route="090")  # I-90 only
alerts = fetch_highway_alerts_rss(county="King")

# Authenticated REST
alerts = get_highway_alerts(
    access_code=ACCESS_CODE,
    state_route="002",
    start_severity="Major",
)

# Active road closures only
closures = get_active_road_closures(access_code=ACCESS_CODE)
# or without auth:
closures = get_active_road_closures()
```

### HighwayAlert Fields

```python
@dataclass
class HighwayAlert:
    alert_id: int
    headline: str
    event_category: str     # "Road Closure", "Construction", "Incident", etc.
    event_status: str       # "Active", "Scheduled", etc.
    start_road_name: str
    start_direction: str
    start_milepost: float
    start_latitude: float
    start_longitude: float
    end_road_name: str
    end_milepost: float
    end_latitude: float
    end_longitude: float
    last_updated: str       # ISO 8601
    start_time: str
    end_time: str
    priority: str           # "Low", "Medium", "High"
    extended_description: str
    region: str
    county: str

    @property
    def is_closure(self) -> bool: ...
```

---

## Weather Stations

### Endpoints

| Type | URL | Auth |
|------|-----|------|
| REST (all) | `https://www.wsdot.wa.gov/Traffic/api/WeatherStation/WeatherStationREST.svc/GetCurrentWeatherInformationAsJson?AccessCode={code}` | AccessCode |
| Single station | `.../GetCurrentStationWeatherInformationAsJson?AccessCode={code}&StationID={id}` | AccessCode |
| RSS feed | `https://www.wsdot.wa.gov/Traffic/api/WeatherStation/rss.aspx` | None |

### Usage

```python
# Public RSS feed
stations = fetch_weather_stations_rss()
stations = fetch_weather_stations_rss(region_code="SC")  # South Central

# Authenticated REST
stations = get_weather_stations(access_code=ACCESS_CODE)
station = get_weather_stations(access_code=ACCESS_CODE, station_id=1234)
```

### WeatherReading Fields

```python
@dataclass
class WeatherReading:
    station_id: int
    station_name: str
    road_name: str
    milepost: float
    region: str
    latitude: float
    longitude: float
    temperature: float          # air temp, Fahrenheit
    road_temperature: float     # pavement temp, Fahrenheit
    surface_condition: str      # "Dry", "Wet", "Ice", "Snow"
    visibility: float           # miles
    wind_speed: float           # mph
    wind_direction: str         # "N", "NE", "E", etc.
    precipitation_type: str     # "None", "Rain", "Snow", "Freezing Rain"
    time_updated: str           # ISO 8601
```

---

## Washington State Ferries

WSF API base URL: `https://www.wsdot.wa.gov/ferries/api/`

All responses use the WSF date format `/Date(milliseconds-offset)/` which is
automatically converted to ISO 8601 by this client.

### Vessel Locations (Real-Time)

```python
# All vessel positions (no auth needed for basic data)
vessels = get_ferry_vessel_locations()

# Only vessels currently underway
in_transit = get_vessels_in_transit()

# Fleet list
fleet = get_ferry_vessels()
```

**Endpoint:** `GET https://www.wsdot.wa.gov/ferries/api/vessels/rest/latest/vessellocations`

### Terminal Information

```python
terminals = get_ferry_terminals()
# Returns list of FerryTerminal with id, name, coordinates, address
```

**Endpoint:** `GET https://www.wsdot.wa.gov/ferries/api/terminals/rest/latest/terminalbasics`

### Schedules

```python
# Today's sailings between Seattle (1) and Bainbridge Island (3)
sailings = get_ferry_schedule_today(
    depart_terminal_id=1,    # Seattle
    arrive_terminal_id=3,    # Bainbridge Island
)

# Specific date
sailings = get_ferry_schedule_today(
    depart_terminal_id=1,
    arrive_terminal_id=3,
    date="2026-03-27",
)

# All routes
routes = get_ferry_routes()
```

### Common Terminal IDs

```python
WSF_TERMINALS = {
    "seattle":      1,
    "bainbridge":   3,
    "bremerton":    4,
    "kingston":     7,
    "edmonds":      8,
    "mukilteo":     9,
    "clinton":      10,
    "fauntleroy":   11,
    "vashon":       12,
    "southworth":   13,
    "pt_townsend":  14,
    "coupeville":   15,
    "anacortes":    2,
    "friday_harbor": 20,
    "orcas":        22,
}
```

### FerryVessel Fields

```python
@dataclass
class FerryVessel:
    vessel_id: int
    vessel_name: str          # e.g. "Wenatchee", "Chimacum"
    abbreviation: str
    mmsi: int                 # AIS MMSI number
    status: str               # VesselWatch status
    speed: float              # knots
    heading: int              # degrees
    latitude: float
    longitude: float
    in_service: bool
    at_dock: bool
    departing_terminal_id: int
    departing_terminal_name: str
    arriving_terminal_id: int
    arriving_terminal_name: str
    scheduled_departure: str  # ISO 8601
    eta: str                  # ISO 8601
    time_updated: str
```

### Additional WSF Endpoints

| Endpoint | URL | Notes |
|----------|-----|-------|
| Vessel verbose | `.../vessels/rest/latest/vesselverbose` | Full specs, capacity, dimensions |
| Terminal wait times | `.../terminals/rest/latest/terminalwaittimes` | Drive-up queue wait |
| Terminal bulletins | `.../terminals/rest/latest/terminalbulletins` | Service alerts |
| Valid routes | `.../schedule/rest/latest/valid` | All route combinations |

---

## Work Zones (WZDx)

WSDOT publishes work zone data in the WZDx v4.2 standard GeoJSON format.
No authentication required.

Spec reference: https://github.com/usdot-jpo-ode/wzdx

### Endpoints

| Data | URL |
|------|-----|
| Work zones | `https://wzdx.wsdot.wa.gov/api/v4/wzdx` |
| Field devices | `https://wzdx.wsdot.wa.gov/api/v4/wzdxfd` |

### Usage

```python
# All work zones
zones = fetch_work_zones()

# Active zones only (optionally filtered by road)
active = get_active_work_zones()
i90_zones = get_active_work_zones(road_name="I-90")

# Field devices (DMS signs, arrow boards)
devices = fetch_wzdx_devices()
```

### WorkZone Fields

```python
@dataclass
class WorkZone:
    feature_id: str
    road_name: str            # e.g. "SR 14"
    direction: str            # "northbound", "both"
    vehicle_impact: str       # "all-lanes-closed", "some-lanes-closed"
    beginning_milepost: float
    ending_milepost: float
    start_date: str           # ISO 8601
    end_date: str
    is_start_date_verified: bool
    description: str
    status: str               # "active", "pending", "planned"
    lane_count: int
    speed_limit: float        # mph (converted from kph)
    geometry_type: str        # "LineString", "MultiPoint"
    coordinates: list         # GeoJSON coordinates

    @property
    def is_active(self) -> bool: ...
```

---

## All Discovered Endpoints

### WSDOT Traveler Information API (13 Services)

Base URL: `https://www.wsdot.wa.gov/Traffic/api/`

All services follow the pattern:
- REST JSON: `{Service}/{Service}REST.svc/Get{Data}AsJson?AccessCode={code}`
- SOAP/WSDL: `{Service}/{Service}REST.svc?wsdl`
- RSS: `{Service}/rss.aspx`

| Service | REST Base | RSS Available |
|---------|-----------|---------------|
| HighwayCameras | `.../HighwayCameras/HighwayCamerasREST.svc` | Yes |
| MountainPassConditions | `.../MountainPassConditions/MountainPassConditionsREST.svc` | Yes |
| TrafficFlow | `.../TrafficFlow/TrafficFlowREST.svc` | Yes |
| TravelTimes | `.../TravelTimes/TravelTimesREST.svc` | Yes |
| HighwayAlerts | `.../HighwayAlerts/HighwayAlertsREST.svc` | Yes |
| WeatherStation | `.../WeatherStation/WeatherStationREST.svc` | Yes |
| CVRestrictions | `.../CVRestrictions/CVRestrictionsREST.svc` | Yes |
| BridgeClearances | `.../BridgeClearances/BridgeClearancesREST.svc` | No |
| BorderCrossings | `.../BorderCrossings/BorderCrossingsREST.svc` | Yes |
| TollRates | `.../TollRates/TollRatesREST.svc` | Yes |

### Public RSS/KML Feeds (No Auth)

```
Cameras RSS:          https://www.wsdot.wa.gov/Traffic/api/HighwayCameras/rss.aspx
Cameras KML:          https://www.wsdot.wa.gov/Traffic/api/HighwayCameras/kml.aspx
Mountain Pass RSS:    https://www.wsdot.wa.gov/Traffic/api/MountainPassConditions/rss.aspx
Traffic Flow RSS:     https://www.wsdot.wa.gov/Traffic/api/TrafficFlow/rss.aspx
Travel Times RSS:     https://www.wsdot.wa.gov/Traffic/api/TravelTimes/rss.aspx
Highway Alerts RSS:   https://www.wsdot.wa.gov/Traffic/api/HighwayAlerts/rss.aspx
Weather Stations RSS: https://www.wsdot.wa.gov/Traffic/api/WeatherStation/rss.aspx
CV Restrictions RSS:  https://www.wsdot.wa.gov/Traffic/api/CVRestrictions/rss.aspx
Border Crossings RSS: https://www.wsdot.wa.gov/Traffic/api/BorderCrossings/rss.aspx
Toll Rates RSS:       https://www.wsdot.wa.gov/Traffic/api/TollRates/rss.aspx
```

### Camera Image CDN (No Auth)

```
Pattern: https://images.wsdot.wa.gov/{region}/{route3d}vc{milepost5d}.jpg
Example: https://images.wsdot.wa.gov/sc/090vc05200.jpg
```

### WSF Ferry API (Optional Auth)

```
Vessel locations:     https://www.wsdot.wa.gov/ferries/api/vessels/rest/latest/vessellocations
Vessel basics:        https://www.wsdot.wa.gov/ferries/api/vessels/rest/latest/vesselbasics
Vessel verbose:       https://www.wsdot.wa.gov/ferries/api/vessels/rest/latest/vesselverbose
Terminal basics:      https://www.wsdot.wa.gov/ferries/api/terminals/rest/latest/terminalbasics
Terminal wait times:  https://www.wsdot.wa.gov/ferries/api/terminals/rest/latest/terminalwaittimes
Terminal bulletins:   https://www.wsdot.wa.gov/ferries/api/terminals/rest/latest/terminalbulletins
Schedule (today):     https://www.wsdot.wa.gov/ferries/api/schedule/rest/latest/scheduletoday/{dep}/{arr}/false
Schedule (date):      https://www.wsdot.wa.gov/ferries/api/schedule/rest/latest/schedule/{dep}/{arr}/{YYYY-MM-DD}
Valid routes:         https://www.wsdot.wa.gov/ferries/api/schedule/rest/latest/valid
```

### WZDx Work Zone GeoJSON (No Auth)

```
Work zones:    https://wzdx.wsdot.wa.gov/api/v4/wzdx
Field devices: https://wzdx.wsdot.wa.gov/api/v4/wzdxfd
```

---

## Data Formats

### WSDOT REST JSON Date Format

WSDOT REST APIs return dates in Microsoft JSON serialization format:

```
/Date(1700000000000-0800)/
```

- Milliseconds since Unix epoch (UTC)
- Optional timezone offset in `-HHMM` or `+HHMM` format

The client automatically converts these to ISO 8601:
```
2023-11-14T22:13:20-08:00
```

### RSS Feed Format

Standard RSS 2.0. Items contain:
- `<title>`: Human-readable name/description
- `<description>`: HTML-escaped text with key:value pairs or HTML table
- `<pubDate>`: RFC 2822 timestamp
- `<link>`: WSDOT website URL for the item

### KML Feed Format

Standard KML 2.2:
```xml
<Placemark>
  <name>Camera Name</name>
  <description>...</description>
  <Point>
    <coordinates>-122.3321,47.6062,0</coordinates>
  </Point>
</Placemark>
```

Coordinates are in `longitude,latitude,altitude` order.

### WZDx GeoJSON Format

Standard GeoJSON FeatureCollection conforming to WZDx v4.2 spec:
```json
{
  "type": "FeatureCollection",
  "features": [
    {
      "type": "Feature",
      "id": "wsdot-wz-12345",
      "geometry": {"type": "LineString", "coordinates": [[...]]},
      "properties": {
        "core_details": {
          "road_names": ["SR 14"],
          "direction": "eastbound",
          "description": "Lane closure for bridge work"
        },
        "vehicle_impact": "some-lanes-closed",
        "event_status": "active",
        "start_date": "2026-03-01T08:00:00Z",
        "end_date": "2026-06-30T18:00:00Z",
        "lanes": []
      }
    }
  ]
}
```

---

## Region & Route Codes

### WSDOT Region Codes (Image CDN)

| Code | Region Name | Coverage |
|------|-------------|----------|
| `er` | Eastern Region | Spokane, Yakima, I-90 east |
| `nc` | North Central Region | Wenatchee, US-2, US-97 |
| `nw` | Northwest Region | Seattle metro, I-5, I-405, SR-99 |
| `ol` | Olympic Region | Olympic Peninsula, US-101 |
| `sc` | South Central Region | Yakima Valley, I-90 passes |
| `sw` | Southwest Region | Vancouver WA, I-205 |
| `wsf` | Washington State Ferries | Ferry terminal cameras |
| `rweather` | Road Weather | Road weather information system cameras |
| `spokane` | Spokane Area | Spokane metro cameras |
| `airports` | Airports | Airport runway/tarmac cameras |
| `traffic` | Generic Traffic | Miscellaneous traffic cameras |

### WSDOT Region Integer Codes (REST API)

| Integer | Region |
|---------|--------|
| 7 | Eastern Region |
| 8 | North Central Region |
| 9 | Northwest Region |
| 10 | Olympic Region |
| 11 | South Central Region |
| 12 | Southwest Region |

### State Route Number Formatting

For REST API `StateRoute` parameter, use zero-padded 3-digit route numbers:

| Highway | StateRoute |
|---------|------------|
| I-5 | `005` |
| I-90 | `090` |
| US-2 | `002` |
| US-12 | `012` |
| US-97 | `097` |
| SR-20 | `020` |
| SR-410 | `410` |
| SR-99 | `099` |

---

## Dependencies

The client uses only Python standard library modules:

```python
import re
import json
import time
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field, asdict
from typing import Optional, List, Dict, Iterator
from datetime import datetime
```

No third-party packages required. Compatible with Python 3.7+.

---

## File Structure

```
wsdot_cams_client.py
|-- Data Models
|   |-- CameraLocation          # GPS + road context
|   |-- Camera                  # Full camera object
|   |-- PassCondition           # Mountain pass (simple)
|   |-- FlowReading             # Traffic flow sensor
|   |-- TravelTimeRoute         # Named travel time route
|   |-- HighwayAlert            # Road incident/closure
|   |-- WeatherReading          # Road weather station
|   |-- MountainPassReport      # Detailed pass conditions
|   |-- FerryVessel             # WSF ferry with position
|   |-- FerryTerminal           # WSF terminal
|   |-- FerryRoute              # WSF route definition
|   |-- FerrySailing            # Individual departure
|   |-- WorkZone                # WZDx work zone
|   +-- WZDxDevice              # WZDx field device
|
|-- WSDOTCameraClient           # Main camera client class
|   |-- get_all_cameras_public()
|   |-- search_cameras_public()
|   |-- get_all_cameras_kml()
|   |-- get_snoqualmie_pass_cameras()
|   |-- get_stevens_pass_cameras()
|   |-- get_white_pass_cameras()
|   |-- get_all_cameras()           # requires AccessCode
|   |-- search_cameras()            # requires AccessCode
|   |-- get_camera()                # requires AccessCode
|   |-- get_all_pass_conditions()   # requires AccessCode
|   |-- get_pass_condition()        # requires AccessCode
|   |-- fetch_camera_image()
|   |-- build_image_url()
|   |-- cameras_to_geojson()
|   +-- cameras_to_csv()
|
|-- Traffic Flow
|   |-- fetch_traffic_flow_rss()    # public
|   +-- get_traffic_flow()          # AccessCode required
|
|-- Travel Times
|   |-- fetch_travel_times_rss()    # public
|   +-- get_travel_times()          # AccessCode required
|
|-- Highway Alerts
|   |-- fetch_highway_alerts_rss()  # public
|   |-- get_highway_alerts()        # AccessCode required
|   +-- get_active_road_closures()  # convenience wrapper
|
|-- Weather Stations
|   |-- fetch_weather_stations_rss() # public
|   +-- get_weather_stations()        # AccessCode required
|
|-- Mountain Pass Conditions
|   |-- fetch_mountain_pass_conditions()  # RSS (public) or REST (auth)
|   +-- get_active_pass_closures()        # convenience
|
|-- Washington State Ferries
|   |-- get_ferry_vessel_locations()
|   |-- get_ferry_vessels()
|   |-- get_ferry_terminals()
|   |-- get_ferry_routes()
|   |-- get_ferry_schedule_today()
|   +-- get_vessels_in_transit()          # convenience
|
|-- Work Zones (WZDx)
|   |-- fetch_work_zones()
|   |-- fetch_wzdx_devices()
|   +-- get_active_work_zones()           # convenience
|
|-- Helper Utilities
|   |-- _to_float()
|   |-- _parse_wsdot_date()
|   +-- _parse_wsf_date()
|
+-- WSDOT_ENDPOINTS             # Reference dictionary of all endpoints
```

---

## API Registration

- WSDOT Traveler Info API: https://www.wsdot.wa.gov/Traffic/api/
- WSF API: https://www.wsdot.wa.gov/ferries/api/
- WZDx GitHub spec: https://github.com/usdot-jpo-ode/wzdx

---

*Reverse-engineered from WSDOT public documentation and live network traffic.
Data is copyright Washington State Department of Transportation.*
