# Formula 1 API Client - Reverse Engineering Report

## Overview

This document details the reverse engineering of Formula 1 data APIs discovered through analysis of the official Formula 1 website (www.formula1.com) and related services.

## Discovered APIs

### 1. Official Formula 1 API (api.formula1.com)

**Base URL**: `https://api.formula1.com`

**Status**: Requires API key authentication

**Discovered Endpoints**:
- `/v2/fom-results` - Race results data
- `/svc/v2/whereami` - Location/geolocation services

**Authentication**: Requires `apikey` header parameter

**Notes**:
- This API is used by the official F1 website
- API keys are embedded in the website's JavaScript bundles
- Unauthorized access returns: `{"error": "Unauthorized", "message": "Failed to resolve API Key variable request.header.apikey"}`
- Not recommended for public use due to authentication requirements

### 2. Formula 1 Live Timing API (livetiming.formula1.com)

**Base URL**: `https://livetiming.formula1.com`

**Discovered Components**:
- `/signalrcore` - WebSocket/SignalR endpoint for real-time data
- `/static/` - Static assets and timing data files

**Notes**:
- Used for live race timing and telemetry
- Requires WebSocket connection with SignalR protocol
- Provides real-time position updates, lap times, and sector times during races

### 3. OpenF1 API (api.openf1.org) - RECOMMENDED

**Base URL**: `https://api.openf1.org/v1`

**Status**: FREE, NO AUTHENTICATION REQUIRED

**Description**: Open-source, community-maintained API providing comprehensive Formula 1 data from recent seasons. This is the API used in the provided Python client.

## OpenF1 API Documentation

### Authentication

None required - completely open access.

### Rate Limiting

The API has rate limiting in place. Recommended practices:
- Cache responses when possible
- Implement delays between requests
- Use specific filters to reduce response size

### Available Endpoints

#### 1. Sessions and Meetings

##### GET /v1/sessions
Get session information (races, qualifying, practice sessions).

**Query Parameters**:
- `year` (int) - Filter by year (e.g., 2024)
- `session_key` (int) - Specific session identifier
- `session_type` (string) - Type: "Race", "Qualifying", "Practice", "Sprint"
- `location` (string) - Location name

**Example**:
```bash
curl "https://api.openf1.org/v1/sessions?year=2024&session_type=Race"
```

**Response Fields**:
- `session_key` - Unique session identifier
- `session_name` - Session name
- `session_type` - Type of session
- `date_start` / `date_end` - Session timing
- `meeting_key` - Parent meeting identifier
- `circuit_short_name` - Circuit name
- `location` - Location
- `country_name` / `country_code` - Country info
- `gmt_offset` - Timezone offset
- `year` - Season year

##### GET /v1/meetings
Get meeting (race weekend) information.

**Query Parameters**:
- `year` (int) - Filter by year
- `meeting_key` (int) - Specific meeting identifier
- `country_name` (string) - Country name

**Response Fields**:
- `meeting_key` - Unique identifier
- `meeting_name` - Weekend name
- `meeting_official_name` - Official title
- `circuit_key` / `circuit_short_name` - Circuit info
- `date_start` / `date_end` - Weekend dates
- `country_flag` - Flag image URL
- `circuit_image` - Circuit layout image

#### 2. Drivers

##### GET /v1/drivers
Get driver information for a session.

**Query Parameters**:
- `session_key` (int) - Session identifier
- `driver_number` (int) - Specific driver number
- `name_acronym` (string) - Driver acronym (e.g., "VER", "HAM")

**Response Fields**:
- `driver_number` - Race number
- `full_name` - Full name
- `name_acronym` - Three-letter code
- `broadcast_name` - Name shown on broadcasts
- `team_name` - Current team
- `team_colour` - Team color (hex)
- `headshot_url` - Driver photo URL
- `country_code` - Nationality

**Example**:
```python
drivers = client.get_drivers(session_key=9472)
verstappen = [d for d in drivers if d['name_acronym'] == 'VER'][0]
```

#### 3. Timing and Positions

##### GET /v1/laps
Get detailed lap timing data.

**Query Parameters**:
- `session_key` (int, required) - Session identifier
- `driver_number` (int) - Filter by driver
- `lap_number` (int) - Specific lap

**Response Fields**:
- `lap_number` - Lap number
- `lap_duration` - Total lap time (seconds)
- `duration_sector_1/2/3` - Sector times
- `i1_speed` / `i2_speed` - Intermediate speeds (km/h)
- `st_speed` - Speed trap
- `is_pit_out_lap` - Boolean flag
- `segments_sector_1/2/3` - Mini-sector performance (2048=green, 2049=yellow, 2051=purple, 2064=invalid)

**Example**:
```python
laps = client.get_laps(session_key=9472, driver_number=1)
fastest = min([l for l in laps if l['lap_duration']], key=lambda x: x['lap_duration'])
```

##### GET /v1/position
Get driver position updates over time.

**Query Parameters**:
- `session_key` (int, required)
- `driver_number` (int) - Filter by driver

**Response Fields**:
- `date` - Timestamp
- `position` - Current position
- `driver_number` - Driver

#### 4. Telemetry

##### GET /v1/car_data
Get car telemetry (speed, throttle, brake, RPM, gear, DRS).

**Query Parameters**:
- `session_key` (int, required)
- `driver_number` (int)
- `speed>=` (int) - Filter for minimum speed

**Response Fields**:
- `date` - Timestamp
- `speed` - Speed (km/h)
- `throttle` - Throttle position (0-100)
- `brake` - Brake pressure (0-100)
- `rpm` - Engine RPM
- `n_gear` - Current gear (0-8)
- `drs` - DRS status (0=closed, 1=open)

**Example**:
```python
# Get high-speed telemetry (>300 km/h)
telemetry = client.get_car_data(session_key=9472, driver_number=1, speed_gte=300)
```

##### GET /v1/location
Get GPS location data for drivers on track.

**Query Parameters**:
- `session_key` (int, required)
- `driver_number` (int)

**Response Fields**:
- `date` - Timestamp
- `x`, `y`, `z` - 3D coordinates

**Note**: Useful for plotting driver positions and overtakes.

#### 5. Race Strategy

##### GET /v1/stints
Get tire stint data.

**Query Parameters**:
- `session_key` (int, required)
- `driver_number` (int)

**Response Fields**:
- `stint_number` - Stint number
- `lap_start` / `lap_end` - Stint range
- `compound` - Tire compound ("SOFT", "MEDIUM", "HARD", "INTERMEDIATE", "WET")
- `tyre_age_at_start` - Age of tires (laps)

**Example**:
```python
stints = client.get_stints(session_key=9472)
for stint in stints:
    print(f"Driver {stint['driver_number']}: {stint['compound']} (Laps {stint['lap_start']}-{stint['lap_end']})")
```

##### GET /v1/pit
Get pit stop data.

**Query Parameters**:
- `session_key` (int, required)
- `driver_number` (int)

**Response Fields**:
- `date` - Pit stop time
- `lap_number` - Lap of pit stop
- `pit_duration` - Total time (seconds)
- `stop_duration` - Time stopped (seconds)
- `lane_duration` - Time in pit lane

#### 6. Race Control and Communications

##### GET /v1/race_control
Get race control messages, flags, and penalties.

**Query Parameters**:
- `session_key` (int, required)
- `driver_number` (int)
- `category` (string) - "Flag", "SafetyCar", "Drs", etc.

**Response Fields**:
- `date` - Message time
- `category` - Type of message
- `message` - Message text
- `flag` - Flag type (GREEN, YELLOW, RED, etc.)
- `scope` - "Track", "Sector", "Driver"
- `sector` - Affected sector (if applicable)

**Example**:
```python
flags = client.get_race_control(session_key=9472, category="Flag")
for flag in flags:
    print(f"{flag['flag']}: {flag['message']}")
```

##### GET /v1/team_radio
Get team radio recordings.

**Query Parameters**:
- `session_key` (int, required)
- `driver_number` (int)

**Response Fields**:
- `date` - Recording time
- `driver_number` - Driver
- `recording_url` - URL to MP3 file

**Example**:
```python
radio = client.get_team_radio(session_key=9472, driver_number=1)
for msg in radio:
    print(f"{msg['date']}: {msg['recording_url']}")
    # Download: client.download_team_radio(msg['recording_url'], 'radio.mp3')
```

#### 7. Weather

##### GET /v1/weather
Get weather conditions during a session.

**Query Parameters**:
- `session_key` (int, required)

**Response Fields**:
- `date` - Measurement time
- `air_temperature` - Air temp (°C)
- `track_temperature` - Track temp (°C)
- `humidity` - Humidity (%)
- `pressure` - Atmospheric pressure (mbar)
- `wind_speed` - Wind speed (km/h)
- `wind_direction` - Wind direction (degrees)
- `rainfall` - Rain indicator (0=no rain, 1=rain)

## Python Client Usage

### Installation

```bash
pip install requests
```

No additional dependencies required.

### Basic Usage

```python
from formula1_client import Formula1Client

# Initialize client
client = Formula1Client()

# Get 2024 races
races = client.get_sessions(year=2024, session_type="Race")
print(f"Found {len(races)} races")

# Get drivers for a specific race
session_key = races[0]['session_key']
drivers = client.get_drivers(session_key=session_key)

# Get lap times
laps = client.get_laps(session_key=session_key, driver_number=1)
fastest = min([l for l in laps if l['lap_duration']], key=lambda x: x['lap_duration'])
print(f"Fastest lap: {fastest['lap_duration']:.3f}s")

# Get car telemetry
telemetry = client.get_car_data(session_key=session_key, driver_number=1)

# Get weather
weather = client.get_weather(session_key=session_key)
```

### Finding Session Keys

Session keys are unique identifiers for each session. To find them:

```python
# Get all 2024 sessions
sessions = client.get_sessions(year=2024)

# Filter for specific race
bahrain_race = [s for s in sessions if s['location'] == 'Sakhir' and s['session_type'] == 'Race'][0]
session_key = bahrain_race['session_key']
```

### Advanced Examples

#### Example 1: Analyze Fastest Laps

```python
# Get all drivers' fastest laps
session_key = 9472  # Bahrain GP 2024
drivers = client.get_drivers(session_key=session_key)

fastest_laps = []
for driver in drivers:
    laps = client.get_laps(session_key=session_key, driver_number=driver['driver_number'])
    valid_laps = [l for l in laps if l['lap_duration']]
    if valid_laps:
        fastest = min(valid_laps, key=lambda x: x['lap_duration'])
        fastest_laps.append({
            'driver': driver['full_name'],
            'time': fastest['lap_duration'],
            'lap': fastest['lap_number']
        })

# Sort by lap time
fastest_laps.sort(key=lambda x: x['time'])
for i, lap in enumerate(fastest_laps[:10], 1):
    print(f"{i}. {lap['driver']}: {lap['time']:.3f}s (Lap {lap['lap']})")
```

#### Example 2: Tire Strategy Comparison

```python
# Compare tire strategies
session_key = 9472
drivers_to_compare = [1, 44, 16]  # Verstappen, Hamilton, Leclerc

for driver_num in drivers_to_compare:
    driver = client.get_drivers(session_key=session_key, driver_number=driver_num)[0]
    stints = client.get_stints(session_key=session_key, driver_number=driver_num)

    print(f"\n{driver['full_name']}:")
    for stint in stints:
        laps = stint['lap_end'] - stint['lap_start'] + 1
        print(f"  Stint {stint['stint_number']}: {stint['compound']} ({laps} laps)")
```

#### Example 3: Weather Analysis

```python
# Track weather changes during session
session_key = 9472
weather_data = client.get_weather(session_key=session_key)

print("Weather progression:")
for i, w in enumerate(weather_data[::10]):  # Sample every 10th reading
    print(f"Time {i*10}: Air={w['air_temperature']}°C, "
          f"Track={w['track_temperature']}°C, "
          f"Rain={bool(w['rainfall'])}")
```

#### Example 4: Telemetry Analysis

```python
# Analyze top speed
session_key = 9472
telemetry = client.get_car_data(session_key=session_key, driver_number=1, speed_gte=300)

if telemetry:
    max_speed = max(telemetry, key=lambda x: x['speed'])
    print(f"Max speed: {max_speed['speed']} km/h")
    print(f"At: {max_speed['date']}")
```

## Data Availability

### Years Available
- **2024**: Full season data available
- **2025**: Full season data available
- **2026**: Partial (only completed sessions)

### Session Types
- **Race**: Main race
- **Qualifying**: Qualifying session (Q1, Q2, Q3)
- **Practice**: Practice sessions (FP1, FP2, FP3)
- **Sprint**: Sprint race (when applicable)

### Data Granularity
- **Timing data**: Per lap
- **Telemetry**: ~4-5 Hz (4-5 samples per second)
- **GPS location**: ~3-4 Hz
- **Weather**: ~1 sample per 10 seconds

## Limitations and Considerations

1. **Rate Limiting**: The OpenF1 API has rate limits. Implement delays between requests and cache responses.

2. **Data Availability**: Not all endpoints have data for all sessions (e.g., 2026 races that haven't occurred yet).

3. **Historical Data**: Older seasons (pre-2023) may have limited or no data.

4. **Live Data**: Real-time data during races may be delayed or require WebSocket connections.

5. **Media URLs**: Team radio recordings and images are hosted on F1's CDN and may expire.

## Legal and Ethical Considerations

- This reverse engineering is for educational purposes
- Formula 1 data and trademarks are property of Formula One World Championship Limited
- The OpenF1 API is community-maintained and separate from official F1 services
- Respect rate limits and API terms of service
- Commercial use may require official licensing from Formula 1

## Additional Resources

- **OpenF1 Documentation**: https://openf1.org/
- **Official F1 Website**: https://www.formula1.com
- **F1 Media Portal**: https://media.formula1.com

## Client File Location

The Python client is available at:
```
/home/node/a0/workspace/1953a0cf-cb87-4f1f-8ec4-f30a8b520bec/workspace/outputs/formula1_client.py
```

## Summary

This reverse engineering effort successfully identified three main API systems:

1. **Official F1 API** (api.formula1.com) - Requires authentication, not suitable for public use
2. **Live Timing API** (livetiming.formula1.com) - Real-time data via WebSocket/SignalR
3. **OpenF1 API** (api.openf1.org) - FREE, open-source, comprehensive data

The provided Python client implements the OpenF1 API, offering:
- 12+ endpoint methods covering all major data types
- No authentication required
- Type hints and comprehensive documentation
- Convenience methods for common operations
- Example usage and integration patterns

The OpenF1 API is the recommended choice for developers seeking to build F1 data applications due to its:
- Free access
- No authentication requirements
- Comprehensive coverage
- Active maintenance
- Rich dataset including telemetry, timing, weather, and communications
