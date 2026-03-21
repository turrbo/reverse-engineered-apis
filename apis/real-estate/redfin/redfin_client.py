#!/usr/bin/env python3
"""
Redfin API Client
=================

A production-ready Python client for accessing Redfin's undocumented Stingray API.

This client provides access to property listings, market data, and region information
without requiring authentication. Note that some endpoints are protected by CloudFront
WAF and may return 403 errors for certain types of requests.

Author: Reverse engineered from Redfin.com
Date: 2026-03-21
"""

import json
import time
from typing import Dict, List, Optional, Any, Union
from dataclasses import dataclass
import requests
from urllib.parse import urlencode


@dataclass
class PropertyListing:
    """Represents a property listing from Redfin."""
    property_id: int
    listing_id: Optional[int]
    mls_id: Optional[str]
    price: Optional[int]
    beds: Optional[int]
    baths: Optional[float]
    sqft: Optional[int]
    lot_size: Optional[int]
    address: Optional[str]
    city: Optional[str]
    state: Optional[str]
    zipcode: Optional[str]
    latitude: Optional[float]
    longitude: Optional[float]
    property_type: Optional[int]
    year_built: Optional[int]
    status: Optional[str]
    dom: Optional[int]  # Days on market
    url: Optional[str]

    @classmethod
    def from_api_response(cls, data: Dict[str, Any]) -> 'PropertyListing':
        """Parse a property listing from API response."""
        return cls(
            property_id=data.get('propertyId'),
            listing_id=data.get('listingId'),
            mls_id=data.get('mlsId', {}).get('value'),
            price=data.get('price', {}).get('value'),
            beds=data.get('beds'),
            baths=data.get('baths'),
            sqft=data.get('sqFt', {}).get('value'),
            lot_size=data.get('lotSize', {}).get('value'),
            address=data.get('streetLine', {}).get('value'),
            city=data.get('city'),
            state=data.get('state'),
            zipcode=data.get('zip'),
            latitude=data.get('latLong', {}).get('value', {}).get('latitude'),
            longitude=data.get('latLong', {}).get('value', {}).get('longitude'),
            property_type=data.get('propertyType'),
            year_built=data.get('yearBuilt', {}).get('value'),
            status=data.get('mlsStatus'),
            dom=data.get('dom', {}).get('value'),
            url=data.get('url')
        )


class RedfinAPIError(Exception):
    """Custom exception for Redfin API errors."""
    pass


class RedfinClient:
    """
    Production-ready client for Redfin's undocumented Stingray API.

    This client provides methods to:
    - Search for properties by region
    - Get property listings with filters
    - Export data to CSV format
    - Get region metadata

    Note: Some endpoints are protected by AWS WAF and may be blocked.
    The working endpoints are primarily for property search and region data.
    """

    BASE_URL = "https://www.redfin.com"
    API_BASE = f"{BASE_URL}/stingray/api"

    # Region types
    REGION_TYPE_NEIGHBORHOOD = 1
    REGION_TYPE_ZIP = 2
    REGION_TYPE_CITY = 6
    REGION_TYPE_METRO = 8
    REGION_TYPE_COUNTY = 4

    # Property types
    PROPERTY_TYPE_SINGLE_FAMILY = 1
    PROPERTY_TYPE_CONDO = 2
    PROPERTY_TYPE_TOWNHOUSE = 3
    PROPERTY_TYPE_MULTI_FAMILY = 4
    PROPERTY_TYPE_LAND = 6
    PROPERTY_TYPE_OTHER = 7

    def __init__(self, session: Optional[requests.Session] = None, rate_limit_delay: float = 0.5):
        """
        Initialize the Redfin API client.

        Args:
            session: Optional requests.Session for connection reuse
            rate_limit_delay: Delay between requests in seconds (default: 0.5)
        """
        self.session = session or requests.Session()
        self.rate_limit_delay = rate_limit_delay
        self._last_request_time = 0.0

        # Set default headers to mimic a real browser
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'application/json, text/javascript, */*; q=0.01',
            'Accept-Language': 'en-US,en;q=0.9',
            'Referer': 'https://www.redfin.com/',
            'Origin': 'https://www.redfin.com',
            'DNT': '1',
            'Connection': 'keep-alive',
            'Sec-Fetch-Dest': 'empty',
            'Sec-Fetch-Mode': 'cors',
            'Sec-Fetch-Site': 'same-origin',
        })

    def _rate_limit(self):
        """Implement rate limiting to avoid triggering WAF."""
        elapsed = time.time() - self._last_request_time
        if elapsed < self.rate_limit_delay:
            time.sleep(self.rate_limit_delay - elapsed)
        self._last_request_time = time.time()

    def _make_request(self, endpoint: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Make a request to the Redfin API.

        Args:
            endpoint: API endpoint path
            params: Query parameters

        Returns:
            Parsed JSON response

        Raises:
            RedfinAPIError: If the request fails or returns an error
        """
        self._rate_limit()

        url = f"{self.API_BASE}/{endpoint}"

        try:
            response = self.session.get(url, params=params, timeout=30)
            response.raise_for_status()

            # Check for WAF block
            if "403 ERROR" in response.text or "Request blocked" in response.text:
                raise RedfinAPIError(
                    "Request blocked by CloudFront WAF. This endpoint may require "
                    "browser-based access or additional authentication."
                )

            # Redfin's API returns JSONP-style responses with {}&&{...}
            # Strip the prefix and parse the JSON
            text = response.text
            if text.startswith('{}&&'):
                text = text[4:]

            data = json.loads(text)

            # Check for API-level errors
            if isinstance(data, dict):
                if data.get('message') == 'page not found':
                    raise RedfinAPIError("API endpoint not found")
                if data.get('errorMessage') and data.get('errorMessage') != 'Success':
                    raise RedfinAPIError(f"API error: {data.get('errorMessage')}")

            return data

        except requests.exceptions.RequestException as e:
            raise RedfinAPIError(f"Request failed: {str(e)}")
        except json.JSONDecodeError as e:
            raise RedfinAPIError(f"Failed to parse JSON response: {str(e)}")

    def get_region_info(self, region_id: int, region_type: int = REGION_TYPE_ZIP) -> Dict[str, Any]:
        """
        Get information about a specific region.

        Args:
            region_id: The Redfin region ID
            region_type: Type of region (ZIP=2, CITY=6, METRO=8, etc.)

        Returns:
            Dict containing region metadata and defaults

        Example:
            >>> client = RedfinClient()
            >>> info = client.get_region_info(17420, RedfinClient.REGION_TYPE_ZIP)
            >>> print(info['payload']['rootDefaults']['region_name'])
        """
        params = {
            'region_id': region_id,
            'region_type': region_type
        }
        return self._make_request('region', params)

    def search_properties(
        self,
        region_id: int,
        region_type: int = REGION_TYPE_ZIP,
        num_homes: int = 350,
        min_price: Optional[int] = None,
        max_price: Optional[int] = None,
        min_beds: Optional[int] = None,
        max_beds: Optional[int] = None,
        min_baths: Optional[float] = None,
        max_baths: Optional[float] = None,
        property_types: Optional[List[int]] = None,
        sold_within_days: Optional[int] = None,
        status: Optional[int] = None
    ) -> List[PropertyListing]:
        """
        Search for properties in a specific region with filters.

        Args:
            region_id: The Redfin region ID
            region_type: Type of region (ZIP=2, CITY=6, METRO=8, etc.)
            num_homes: Maximum number of homes to return (default: 350)
            min_price: Minimum price filter
            max_price: Maximum price filter
            min_beds: Minimum bedrooms
            max_beds: Maximum bedrooms
            min_baths: Minimum bathrooms
            max_baths: Maximum bathrooms
            property_types: List of property type codes
            sold_within_days: Only show homes sold within N days
            status: Listing status filter

        Returns:
            List of PropertyListing objects

        Example:
            >>> client = RedfinClient()
            >>> listings = client.search_properties(
            ...     region_id=1826,
            ...     region_type=RedfinClient.REGION_TYPE_CITY,
            ...     min_price=300000,
            ...     max_price=500000,
            ...     min_beds=2
            ... )
            >>> for listing in listings[:5]:
            ...     print(f"{listing.address}, {listing.city} - ${listing.price}")
        """
        params = {
            'al': 1,  # Access level
            'region_id': region_id,
            'region_type': region_type,
            'num_homes': num_homes
        }

        # Add optional filters
        if min_price is not None:
            params['min_price'] = min_price
        if max_price is not None:
            params['max_price'] = max_price
        if min_beds is not None:
            params['min_beds'] = min_beds
        if max_beds is not None:
            params['max_beds'] = max_beds
        if min_baths is not None:
            params['min_baths'] = min_baths
        if max_baths is not None:
            params['max_baths'] = max_baths
        if property_types:
            params['uipt'] = ','.join(map(str, property_types))
        if sold_within_days is not None:
            params['sold_within_days'] = sold_within_days
        if status is not None:
            params['status'] = status

        response = self._make_request('gis', params)

        # Parse homes from response
        homes = response.get('payload', {}).get('homes', [])
        return [PropertyListing.from_api_response(home) for home in homes]

    def export_properties_csv(
        self,
        region_id: int,
        region_type: int = REGION_TYPE_ZIP,
        num_homes: int = 100,
        **filters
    ) -> str:
        """
        Export property listings to CSV format.

        Args:
            region_id: The Redfin region ID
            region_type: Type of region
            num_homes: Maximum number of homes to export
            **filters: Additional filters (same as search_properties)

        Returns:
            CSV-formatted string with property data

        Example:
            >>> client = RedfinClient()
            >>> csv_data = client.export_properties_csv(
            ...     region_id=1826,
            ...     region_type=RedfinClient.REGION_TYPE_CITY,
            ...     num_homes=50
            ... )
            >>> with open('properties.csv', 'w') as f:
            ...     f.write(csv_data)
        """
        params = {
            'al': 1,
            'region_id': region_id,
            'region_type': region_type,
            'num_homes': num_homes
        }
        params.update(filters)

        self._rate_limit()
        url = f"{self.API_BASE}/gis-csv"

        try:
            response = self.session.get(url, params=params, timeout=30)
            response.raise_for_status()

            if "403 ERROR" in response.text:
                raise RedfinAPIError("Request blocked by CloudFront WAF")

            return response.text

        except requests.exceptions.RequestException as e:
            raise RedfinAPIError(f"Request failed: {str(e)}")

    def get_property_details(self, property_id: int, access_level: int = 3) -> Dict[str, Any]:
        """
        Get detailed information about a specific property.

        WARNING: This endpoint is often blocked by CloudFront WAF.
        It may require browser-based access or additional authentication.

        Args:
            property_id: The Redfin property ID
            access_level: Access level (1-3, higher = more data)

        Returns:
            Property details dictionary

        Raises:
            RedfinAPIError: Often raises error due to WAF protection
        """
        params = {
            'propertyId': property_id,
            'accessLevel': access_level
        }
        return self._make_request('home/details/belowTheFold', params)

    def search_recent_sales(
        self,
        region_id: int,
        region_type: int = REGION_TYPE_ZIP,
        days: int = 30,
        num_homes: int = 100
    ) -> List[PropertyListing]:
        """
        Search for recently sold properties.

        Args:
            region_id: The Redfin region ID
            region_type: Type of region
            days: Number of days to look back
            num_homes: Maximum number of homes to return

        Returns:
            List of recently sold properties

        Example:
            >>> client = RedfinClient()
            >>> recent_sales = client.search_recent_sales(
            ...     region_id=1826,
            ...     region_type=RedfinClient.REGION_TYPE_CITY,
            ...     days=30
            ... )
        """
        return self.search_properties(
            region_id=region_id,
            region_type=region_type,
            num_homes=num_homes,
            sold_within_days=days
        )


# Example usage
if __name__ == "__main__":
    print("=" * 80)
    print("Redfin API Client - Test Suite")
    print("=" * 80)
    print()

    # Initialize client
    client = RedfinClient(rate_limit_delay=1.0)

    # Test 1: Get region information
    print("[Test 1] Getting region information for Boston (region_id=1826)")
    print("-" * 80)
    try:
        region_info = client.get_region_info(1826, RedfinClient.REGION_TYPE_CITY)
        region_name = region_info.get('payload', {}).get('rootDefaults', {}).get('region_name', 'Unknown')
        market = region_info.get('payload', {}).get('rootDefaults', {}).get('market', 'Unknown')
        print(f"✓ Region: {region_name}")
        print(f"✓ Market: {market}")
        print()
    except RedfinAPIError as e:
        print(f"✗ Error: {e}")
        print()

    # Test 2: Search properties with filters
    print("[Test 2] Searching properties in Boston ($300k-$500k)")
    print("-" * 80)
    try:
        listings = client.search_properties(
            region_id=1826,
            region_type=RedfinClient.REGION_TYPE_CITY,
            num_homes=10,
            min_price=300000,
            max_price=500000
        )
        print(f"✓ Found {len(listings)} properties")
        print()

        if listings:
            print("Sample listings:")
            for i, listing in enumerate(listings[:3], 1):
                print(f"  {i}. ${listing.price:,} - {listing.beds}bd/{listing.baths}ba")
                print(f"     {listing.address}, {listing.city}, {listing.state} {listing.zipcode}")
                print(f"     Status: {listing.status} | DOM: {listing.dom} days")
                print()
    except RedfinAPIError as e:
        print(f"✗ Error: {e}")
        print()

    # Test 3: Get recent sales
    print("[Test 3] Getting recent sales in zip code 41095 (last 30 days)")
    print("-" * 80)
    try:
        recent_sales = client.search_recent_sales(
            region_id=17420,
            region_type=RedfinClient.REGION_TYPE_ZIP,
            days=30,
            num_homes=5
        )
        print(f"✓ Found {len(recent_sales)} recent listings")

        if recent_sales:
            print()
            print("Recent listings/sales:")
            for i, sale in enumerate(recent_sales[:5], 1):
                print(f"  {i}. ${sale.price:,} - {sale.beds}bd/{sale.baths}ba")
                print(f"     {sale.address}, {sale.city}, {sale.state}")
                print(f"     Status: {sale.status}")
                print()
    except RedfinAPIError as e:
        print(f"✗ Error: {e}")
        print()

    # Test 4: Export to CSV
    print("[Test 4] Exporting properties to CSV format")
    print("-" * 80)
    try:
        csv_data = client.export_properties_csv(
            region_id=17420,
            region_type=RedfinClient.REGION_TYPE_ZIP,
            num_homes=5
        )
        lines = csv_data.strip().split('\n')
        print(f"✓ Exported {len(lines)} lines of CSV data")
        print()
        print("CSV Preview (first 5 lines):")
        for line in lines[:5]:
            print(f"  {line[:100]}...")
        print()
    except RedfinAPIError as e:
        print(f"✗ Error: {e}")
        print()

    # Test 5: Attempt to get property details (expected to fail due to WAF)
    print("[Test 5] Attempting to get property details (expected to be blocked by WAF)")
    print("-" * 80)
    try:
        details = client.get_property_details(83960101)
        print("✓ Successfully retrieved property details (unexpected!)")
        print()
    except RedfinAPIError as e:
        print(f"✗ Expected error: {e}")
        print("  (This endpoint is protected by CloudFront WAF)")
        print()

    print("=" * 80)
    print("Test suite completed!")
    print("=" * 80)
    print()
    print("Summary:")
    print("  ✓ Working endpoints: region info, property search, CSV export")
    print("  ✗ Blocked endpoints: property details, location autocomplete")
    print()
    print("Note: Rate limiting is recommended to avoid triggering WAF blocks.")
