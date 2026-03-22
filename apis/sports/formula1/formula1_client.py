#!/usr/bin/env python3
"""
Formula 1 API Client - OpenF1 API Wrapper

This client provides easy access to Formula 1 data using the OpenF1 API,
a free and open-source API providing real-time and historical F1 data.

OpenF1 API provides:
- Session data (races, qualifying, practice)
- Driver information and positions
- Car telemetry (speed, throttle, RPM, etc.)
- Lap times and sector times
- Pit stops and tire strategies
- Weather conditions
- Race control messages
- Team radio recordings
- GPS location data

API Documentation: https://openf1.org/
"""

import requests
from typing import Optional, List, Dict, Any, Union
from datetime import datetime
import json


class Formula1Client:
    """
    Client for interacting with the OpenF1 API.

    This API does not require authentication and provides comprehensive
    Formula 1 data from recent seasons.
    """

    BASE_URL = "https://api.openf1.org/v1"

    def __init__(self, timeout: int = 30):
        """
        Initialize the F1 API client.

        Args:
            timeout: Request timeout in seconds (default: 30)
        """
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Formula1-Python-Client/1.0',
            'Accept': 'application/json'
        })
        self.timeout = timeout

    def _get(self, endpoint: str, params: Optional[Dict[str, Any]] = None) -> Union[List[Dict], Dict]:
        """
        Make a GET request to the API.

        Args:
            endpoint: API endpoint path
            params: Query parameters

        Returns:
            JSON response data

        Raises:
            requests.exceptions.RequestException: If request fails
        """
        url = f"{self.BASE_URL}/{endpoint}"
        response = self.session.get(url, params=params, timeout=self.timeout)
        response.raise_for_status()
        return response.json()

    # ============================================================================
    # SESSIONS AND MEETINGS
    # ============================================================================

    def get_sessions(self,
                     year: Optional[int] = None,
                     session_key: Optional[int] = None,
                     session_type: Optional[str] = None,
                     location: Optional[str] = None) -> List[Dict]:
        """
        Get session information.

        Args:
            year: Filter by year (e.g., 2024)
            session_key: Specific session identifier
            session_type: Type of session (e.g., "Race", "Qualifying", "Practice")
            location: Location name

        Returns:
            List of sessions with metadata

        Example:
            >>> client.get_sessions(year=2024, session_type="Race")
        """
        params = {}
        if year:
            params['year'] = year
        if session_key:
            params['session_key'] = session_key
        if session_type:
            params['session_type'] = session_type
        if location:
            params['location'] = location

        return self._get('sessions', params)

    def get_meetings(self,
                     year: Optional[int] = None,
                     meeting_key: Optional[int] = None,
                     country_name: Optional[str] = None) -> List[Dict]:
        """
        Get meeting (race weekend) information.

        Args:
            year: Filter by year
            meeting_key: Specific meeting identifier
            country_name: Country name

        Returns:
            List of meetings with details

        Example:
            >>> client.get_meetings(year=2024)
        """
        params = {}
        if year:
            params['year'] = year
        if meeting_key:
            params['meeting_key'] = meeting_key
        if country_name:
            params['country_name'] = country_name

        return self._get('meetings', params)

    # ============================================================================
    # DRIVERS
    # ============================================================================

    def get_drivers(self,
                   session_key: Optional[int] = None,
                   driver_number: Optional[int] = None,
                   name_acronym: Optional[str] = None) -> List[Dict]:
        """
        Get driver information.

        Args:
            session_key: Filter by session
            driver_number: Specific driver number
            name_acronym: Driver acronym (e.g., "VER", "HAM")

        Returns:
            List of drivers with details

        Example:
            >>> client.get_drivers(session_key=9468)
            >>> client.get_drivers(driver_number=1)
        """
        params = {}
        if session_key:
            params['session_key'] = session_key
        if driver_number:
            params['driver_number'] = driver_number
        if name_acronym:
            params['name_acronym'] = name_acronym

        return self._get('drivers', params)

    # ============================================================================
    # TIMING AND POSITIONS
    # ============================================================================

    def get_laps(self,
                session_key: int,
                driver_number: Optional[int] = None,
                lap_number: Optional[int] = None) -> List[Dict]:
        """
        Get lap timing data.

        Args:
            session_key: Session identifier (required)
            driver_number: Filter by driver
            lap_number: Specific lap number

        Returns:
            List of laps with sector times, speeds, and segments

        Example:
            >>> client.get_laps(session_key=9468, driver_number=1)
        """
        params = {'session_key': session_key}
        if driver_number:
            params['driver_number'] = driver_number
        if lap_number:
            params['lap_number'] = lap_number

        return self._get('laps', params)

    def get_position(self,
                    session_key: int,
                    driver_number: Optional[int] = None) -> List[Dict]:
        """
        Get driver positions during a session.

        Args:
            session_key: Session identifier (required)
            driver_number: Filter by driver

        Returns:
            List of position updates over time

        Example:
            >>> client.get_position(session_key=9468, driver_number=1)
        """
        params = {'session_key': session_key}
        if driver_number:
            params['driver_number'] = driver_number

        return self._get('position', params)

    # ============================================================================
    # TELEMETRY
    # ============================================================================

    def get_car_data(self,
                    session_key: int,
                    driver_number: Optional[int] = None,
                    speed_gte: Optional[int] = None) -> List[Dict]:
        """
        Get car telemetry data.

        Includes: throttle, brake, speed, RPM, gear, DRS

        Args:
            session_key: Session identifier (required)
            driver_number: Filter by driver
            speed_gte: Filter for speed >= value

        Returns:
            List of telemetry data points

        Example:
            >>> client.get_car_data(session_key=9468, driver_number=1, speed_gte=300)
        """
        params = {'session_key': session_key}
        if driver_number:
            params['driver_number'] = driver_number
        if speed_gte:
            params['speed>='] = speed_gte

        return self._get('car_data', params)

    def get_location(self,
                    session_key: int,
                    driver_number: Optional[int] = None) -> List[Dict]:
        """
        Get GPS location data for drivers on track.

        Args:
            session_key: Session identifier (required)
            driver_number: Filter by driver

        Returns:
            List of GPS coordinates over time

        Example:
            >>> client.get_location(session_key=9468, driver_number=1)
        """
        params = {'session_key': session_key}
        if driver_number:
            params['driver_number'] = driver_number

        return self._get('location', params)

    # ============================================================================
    # RACE STRATEGY
    # ============================================================================

    def get_stints(self,
                  session_key: int,
                  driver_number: Optional[int] = None) -> List[Dict]:
        """
        Get tire stint data.

        Args:
            session_key: Session identifier (required)
            driver_number: Filter by driver

        Returns:
            List of stints with compound and tire age

        Example:
            >>> client.get_stints(session_key=9468)
        """
        params = {'session_key': session_key}
        if driver_number:
            params['driver_number'] = driver_number

        return self._get('stints', params)

    def get_pit_stops(self,
                     session_key: int,
                     driver_number: Optional[int] = None) -> List[Dict]:
        """
        Get pit stop data.

        Args:
            session_key: Session identifier (required)
            driver_number: Filter by driver

        Returns:
            List of pit stops with durations

        Example:
            >>> client.get_pit_stops(session_key=9468)
        """
        params = {'session_key': session_key}
        if driver_number:
            params['driver_number'] = driver_number

        return self._get('pit', params)

    # ============================================================================
    # RACE CONTROL AND COMMUNICATIONS
    # ============================================================================

    def get_race_control(self,
                        session_key: int,
                        driver_number: Optional[int] = None,
                        category: Optional[str] = None) -> List[Dict]:
        """
        Get race control messages and flags.

        Args:
            session_key: Session identifier (required)
            driver_number: Filter by driver
            category: Message category (e.g., "Flag", "SafetyCar")

        Returns:
            List of race control messages

        Example:
            >>> client.get_race_control(session_key=9468, category="Flag")
        """
        params = {'session_key': session_key}
        if driver_number:
            params['driver_number'] = driver_number
        if category:
            params['category'] = category

        return self._get('race_control', params)

    def get_team_radio(self,
                      session_key: int,
                      driver_number: Optional[int] = None) -> List[Dict]:
        """
        Get team radio recordings.

        Args:
            session_key: Session identifier (required)
            driver_number: Filter by driver

        Returns:
            List of radio messages with recording URLs

        Example:
            >>> client.get_team_radio(session_key=9468, driver_number=1)
        """
        params = {'session_key': session_key}
        if driver_number:
            params['driver_number'] = driver_number

        return self._get('team_radio', params)

    # ============================================================================
    # WEATHER
    # ============================================================================

    def get_weather(self, session_key: int) -> List[Dict]:
        """
        Get weather conditions during a session.

        Includes: air temperature, track temperature, humidity, pressure,
                 wind speed/direction, rainfall

        Args:
            session_key: Session identifier (required)

        Returns:
            List of weather updates

        Example:
            >>> client.get_weather(session_key=9468)
        """
        params = {'session_key': session_key}
        return self._get('weather', params)

    # ============================================================================
    # CONVENIENCE METHODS
    # ============================================================================

    def get_latest_race(self) -> Optional[Dict]:
        """
        Get the most recent race session.

        Returns:
            Latest race session data or None
        """
        current_year = datetime.now().year
        sessions = self.get_sessions(year=current_year, session_type="Race")

        if not sessions:
            # Try previous year
            sessions = self.get_sessions(year=current_year - 1, session_type="Race")

        if sessions:
            # Sort by date and return most recent
            sessions_sorted = sorted(sessions, key=lambda x: x.get('date_start', ''), reverse=True)
            return sessions_sorted[0]

        return None

    def get_driver_standings(self, session_key: int) -> List[Dict]:
        """
        Get driver positions at the end of a session.

        Args:
            session_key: Session identifier

        Returns:
            List of drivers sorted by final position
        """
        positions = self.get_position(session_key=session_key)

        if not positions:
            return []

        # Group by driver and get final position
        driver_final_positions = {}
        for pos in positions:
            driver_num = pos['driver_number']
            date = pos['date']
            if driver_num not in driver_final_positions or date > driver_final_positions[driver_num]['date']:
                driver_final_positions[driver_num] = pos

        # Sort by position
        standings = sorted(driver_final_positions.values(), key=lambda x: x['position'])

        return standings

    def get_fastest_lap(self, session_key: int) -> Optional[Dict]:
        """
        Get the fastest lap in a session.

        Args:
            session_key: Session identifier

        Returns:
            Lap data for fastest lap or None
        """
        laps = self.get_laps(session_key=session_key)

        if not laps:
            return None

        # Filter out laps without duration
        valid_laps = [lap for lap in laps if lap.get('lap_duration')]

        if not valid_laps:
            return None

        # Find fastest
        fastest = min(valid_laps, key=lambda x: x['lap_duration'])

        return fastest

    def get_season_races(self, year: int) -> List[Dict]:
        """
        Get all race sessions for a season.

        Args:
            year: Season year

        Returns:
            List of race sessions
        """
        return self.get_sessions(year=year, session_type="Race")

    def download_team_radio(self, recording_url: str, output_path: str) -> bool:
        """
        Download a team radio recording.

        Args:
            recording_url: URL to the MP3 file
            output_path: Local path to save the file

        Returns:
            True if successful, False otherwise
        """
        try:
            response = self.session.get(recording_url, timeout=self.timeout)
            response.raise_for_status()

            with open(output_path, 'wb') as f:
                f.write(response.content)

            return True
        except Exception as e:
            print(f"Error downloading radio: {e}")
            return False


# ============================================================================
# EXAMPLE USAGE
# ============================================================================

if __name__ == "__main__":
    # Initialize client
    client = Formula1Client()

    print("=" * 80)
    print("Formula 1 API Client - Example Usage")
    print("=" * 80)
    print()

    # Use 2024 Bahrain GP Race for demonstration
    print("1. Getting 2024 Bahrain Grand Prix race...")
    session_key = 9472  # 2024 Bahrain GP Race
    print(f"   Using session key: {session_key}")

    print()

    # Get drivers in session
    print("2. Getting drivers...")
    drivers = client.get_drivers(session_key=session_key)
    print(f"   Found {len(drivers)} drivers")
    if drivers:
        for i, driver in enumerate(drivers[:3]):  # Show first 3
            print(f"   {i+1}. {driver['full_name']} ({driver['name_acronym']}) - {driver['team_name']}")

    print()
    print("3. API Endpoints Available:")
    print("   - get_sessions() - Get session information")
    print("   - get_meetings() - Get race weekend details")
    print("   - get_drivers() - Get driver data")
    print("   - get_laps() - Get lap times and sectors")
    print("   - get_position() - Get driver positions")
    print("   - get_car_data() - Get telemetry (speed, throttle, RPM, etc.)")
    print("   - get_location() - Get GPS coordinates")
    print("   - get_stints() - Get tire strategy")
    print("   - get_pit_stops() - Get pit stop data")
    print("   - get_race_control() - Get race control messages")
    print("   - get_team_radio() - Get team radio recordings")
    print("   - get_weather() - Get weather conditions")

    print()
    print("4. Example Usage:")
    print("   # Get all 2024 races")
    print("   races = client.get_sessions(year=2024, session_type='Race')")
    print()
    print("   # Get lap times for a specific driver")
    print("   laps = client.get_laps(session_key=9472, driver_number=1)")
    print()
    print("   # Get car telemetry")
    print("   telemetry = client.get_car_data(session_key=9472, driver_number=1)")
    print()
    print("   # Get weather")
    print("   weather = client.get_weather(session_key=9472)")

    print()
    print("=" * 80)
    print("Example completed successfully!")
    print("=" * 80)
