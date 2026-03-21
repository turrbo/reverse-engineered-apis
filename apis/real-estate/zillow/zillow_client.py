#!/usr/bin/env python3
"""
Zillow API Client (Unofficial)

This client provides access to Zillow's internal APIs discovered through reverse engineering.
Note: Zillow uses PerimeterX bot protection on most endpoints, limiting what can be accessed
without a browser session. This client focuses on publicly accessible endpoints.

Author: Reverse Engineered
Date: 2026-03-21
"""

import requests
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from enum import Enum
import json
import time


class RegionType(Enum):
    """Zillow region types"""
    REGION = "Region"
    ADDRESS = "Address"
    ZIPCODE = "zipcode"
    CITY = "city"
    STATE = "state"
    NEIGHBORHOOD = "neighborhood"


@dataclass
class Location:
    """Represents a location result from autocomplete"""
    display: str
    result_type: str
    region_id: Optional[int] = None
    region_type: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zipcode: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    zpid: Optional[int] = None

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Location':
        """Create Location from API response"""
        meta = data.get('metaData', {})
        return cls(
            display=data.get('display', ''),
            result_type=data.get('resultType', ''),
            region_id=meta.get('regionId'),
            region_type=meta.get('regionType'),
            city=meta.get('city'),
            state=meta.get('state'),
            zipcode=meta.get('zipCode') or meta.get('zipcode'),
            latitude=meta.get('lat'),
            longitude=meta.get('lng'),
            zpid=meta.get('zpid')
        )


@dataclass
class PropertyValueHistory:
    """Represents historical property value data"""
    dates: List[str]
    values: List[float]
    zpid: str

    @classmethod
    def from_tsv(cls, tsv_data: str) -> 'PropertyValueHistory':
        """Parse TSV data from HomeValueChartData endpoint"""
        lines = tsv_data.strip().split('\n')
        dates = []
        values = []
        zpid = None

        for line in lines[1:]:  # Skip header
            parts = line.split('\t')
            if len(parts) >= 3:
                dates.append(parts[0])
                try:
                    values.append(float(parts[1]))
                except ValueError:
                    continue
                if zpid is None:
                    zpid = parts[2]

        return cls(dates=dates, values=values, zpid=zpid or "unknown")


class ZillowClient:
    """
    Unofficial Zillow API Client

    Discovered Endpoints:
    1. Autocomplete API - Search for locations, addresses, and properties
    2. Home Value Chart Data - Get historical property values (Zestimate history)

    Note: Most Zillow endpoints are protected by PerimeterX bot detection and require
    browser-based access with valid cookies and tokens.
    """

    BASE_URL = "https://www.zillow.com"
    STATIC_URL = "https://www.zillowstatic.com"

    def __init__(self, timeout: int = 10, user_agent: Optional[str] = None):
        """
        Initialize Zillow API Client

        Args:
            timeout: Request timeout in seconds
            user_agent: Custom user agent string (uses default if not provided)
        """
        self.timeout = timeout
        self.session = requests.Session()

        self.user_agent = user_agent or (
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 '
            '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        )

        self.session.headers.update({
            'User-Agent': self.user_agent,
            'Accept': 'application/json, text/plain, */*',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'DNT': '1',
            'Connection': 'keep-alive',
        })

    def autocomplete(self, query: str) -> List[Location]:
        """
        Search for locations, addresses, and properties using autocomplete

        This endpoint is publicly accessible and doesn't require authentication.
        Returns results for cities, zip codes, addresses, and specific properties.

        Args:
            query: Search query (e.g., "Beverly Hills, CA", "90210", "123 Main St")

        Returns:
            List of Location objects matching the query

        Example:
            >>> client = ZillowClient()
            >>> results = client.autocomplete("New York, NY")
            >>> for loc in results:
            ...     print(f"{loc.display} - {loc.result_type}")
        """
        url = f"{self.STATIC_URL}/autocomplete/v3/suggestions"
        params = {'q': query}

        try:
            response = self.session.get(
                url,
                params=params,
                timeout=self.timeout
            )
            response.raise_for_status()

            data = response.json()
            results = data.get('results', [])

            return [Location.from_dict(r) for r in results]

        except requests.RequestException as e:
            raise Exception(f"Autocomplete API error: {e}")

    def get_property_value_history(self, zpid: str) -> PropertyValueHistory:
        """
        Get historical property value data (Zestimate history)

        This endpoint returns the Zestimate (Zillow's estimated market value) history
        for a specific property identified by its ZPID.

        Args:
            zpid: Zillow Property ID (can be obtained from autocomplete results)

        Returns:
            PropertyValueHistory object with dates and values

        Example:
            >>> client = ZillowClient()
            >>> history = client.get_property_value_history("20533168")
            >>> print(f"Latest value: ${history.values[-1]:,.0f}")

        Note:
            This endpoint works for some ZPIDs but may return 403 for others
            depending on property status and bot detection.
        """
        url = f"{self.BASE_URL}/ajax/homedetail/HomeValueChartData.htm"
        params = {
            'zpid': zpid,
            'mt': '1'  # Market type
        }

        try:
            response = self.session.get(
                url,
                params=params,
                timeout=self.timeout
            )

            if response.status_code == 403:
                raise Exception(
                    "Access denied (403). This ZPID may be blocked by bot protection."
                )

            response.raise_for_status()

            return PropertyValueHistory.from_tsv(response.text)

        except requests.RequestException as e:
            raise Exception(f"Property value history API error: {e}")

    def search_properties(self, location: str) -> List[Location]:
        """
        Search for properties in a specific location

        This is a convenience method that uses the autocomplete API
        to find properties matching an address or location.

        Args:
            location: Address or location to search

        Returns:
            List of Location objects, filtered to Address type results

        Example:
            >>> client = ZillowClient()
            >>> properties = client.search_properties("1600 Amphitheatre Parkway")
            >>> for prop in properties:
            ...     print(f"{prop.display} (ZPID: {prop.zpid})")
        """
        results = self.autocomplete(location)
        return [r for r in results if r.result_type == "Address" and r.zpid]

    def search_regions(self, location: str) -> List[Location]:
        """
        Search for regions (cities, zip codes, neighborhoods)

        This is a convenience method that uses the autocomplete API
        to find regions matching a location query.

        Args:
            location: Location query (city, state, zip code, etc.)

        Returns:
            List of Location objects, filtered to Region type results

        Example:
            >>> client = ZillowClient()
            >>> regions = client.search_regions("California")
            >>> for region in regions:
            ...     print(f"{region.display} - Region ID: {region.region_id}")
        """
        results = self.autocomplete(location)
        return [r for r in results if r.result_type == "Region"]

    # Protected/Limited Endpoints (documented but may not work without browser session)

    def _graphql_query(self, query: str, variables: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute a GraphQL query against Zillow's GraphQL endpoint

        WARNING: This endpoint uses persisted queries (safelist) and requires
        specific query hashes. It will return 403 "QUERY_NOT_IN_SAFELIST" for
        non-whitelisted queries.

        This method is included for documentation purposes but will not work
        without valid persisted query hashes obtained from Zillow's frontend.

        Args:
            query: GraphQL query string
            variables: Query variables

        Returns:
            GraphQL response data

        Raises:
            Exception: Always fails with QUERY_NOT_IN_SAFELIST
        """
        url = f"{self.BASE_URL}/graphql/"

        payload = {
            'query': query,
            'variables': variables
        }

        response = self.session.post(
            url,
            json=payload,
            timeout=self.timeout
        )

        if response.status_code != 200:
            raise Exception(f"GraphQL error: {response.text}")

        return response.json()

    def __repr__(self) -> str:
        return f"ZillowClient(timeout={self.timeout})"


# Example usage and testing
if __name__ == "__main__":
    print("=" * 70)
    print("Zillow API Client - Test Run")
    print("=" * 70)

    client = ZillowClient()

    # Test 1: Autocomplete search
    print("\n1. Testing Autocomplete API")
    print("-" * 70)
    try:
        results = client.autocomplete("Beverly Hills, CA")
        print(f"✓ Found {len(results)} results for 'Beverly Hills, CA'")
        for i, loc in enumerate(results[:3], 1):
            print(f"  {i}. {loc.display}")
            print(f"     Type: {loc.result_type}")
            if loc.region_id:
                print(f"     Region ID: {loc.region_id}")
            if loc.zpid:
                print(f"     ZPID: {loc.zpid}")
            if loc.latitude and loc.longitude:
                print(f"     Coordinates: ({loc.latitude:.4f}, {loc.longitude:.4f})")
    except Exception as e:
        print(f"✗ Error: {e}")

    # Test 2: Search for specific address
    print("\n2. Testing Property Search")
    print("-" * 70)
    try:
        properties = client.search_properties("1600 Amphitheatre Parkway")
        print(f"✓ Found {len(properties)} properties")
        for prop in properties[:3]:
            print(f"  - {prop.display}")
            if prop.zpid:
                print(f"    ZPID: {prop.zpid}")
    except Exception as e:
        print(f"✗ Error: {e}")

    # Test 3: Get property value history (using a known working ZPID)
    print("\n3. Testing Property Value History")
    print("-" * 70)
    test_zpid = "20533168"  # Known working ZPID
    try:
        history = client.get_property_value_history(test_zpid)
        print(f"✓ Retrieved {len(history.values)} data points for ZPID {test_zpid}")
        print(f"  Date range: {history.dates[0]} to {history.dates[-1]}")
        print(f"  Latest value: ${history.values[-1]:,.0f}")
        print(f"  Earliest value: ${history.values[0]:,.0f}")
        value_change = history.values[-1] - history.values[0]
        pct_change = (value_change / history.values[0]) * 100
        print(f"  Change: ${value_change:,.0f} ({pct_change:+.1f}%)")
    except Exception as e:
        print(f"✗ Error: {e}")

    # Test 4: Region search
    print("\n4. Testing Region Search")
    print("-" * 70)
    try:
        regions = client.search_regions("90210")
        print(f"✓ Found {len(regions)} regions for '90210'")
        for region in regions[:3]:
            print(f"  - {region.display}")
            print(f"    Region Type: {region.region_type}")
            if region.region_id:
                print(f"    Region ID: {region.region_id}")
    except Exception as e:
        print(f"✗ Error: {e}")

    # Test 5: Search NYC properties
    print("\n5. Testing NYC Property Search")
    print("-" * 70)
    try:
        results = client.autocomplete("New York, NY 10001")
        print(f"✓ Found {len(results)} results for 'New York, NY 10001'")
        for result in results[:5]:
            print(f"  - {result.display} ({result.result_type})")
    except Exception as e:
        print(f"✗ Error: {e}")

    print("\n" + "=" * 70)
    print("Test run complete!")
    print("=" * 70)
    print("\nNOTE: Most Zillow endpoints require browser-based access due to")
    print("PerimeterX bot protection. This client provides access to the")
    print("publicly available endpoints that can be accessed programmatically.")
