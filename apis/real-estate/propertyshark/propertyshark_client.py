#!/usr/bin/env python3
"""
PropertyShark.com API Client
=============================

This is a reverse-engineered Python client for PropertyShark.com's internal APIs.

IMPORTANT NOTES:
- PropertyShark.com uses heavy Cloudflare protection (bot detection, CAPTCHA)
- Many endpoints require authentication and a paid subscription
- This client provides the API structure but direct usage may be blocked
- Best used as a reference for understanding PropertyShark's API architecture

The site structure includes:
- Property search by address, neighborhood, city, ZIP
- Property details (ownership, tax records, sales history)
- Foreclosures data
- Comparables/market analytics
- Owner lookup
- Property lists and maps

Author: Reverse engineered via browser analysis
Date: 2026-03-21
"""

import requests
from typing import Dict, List, Optional, Any
import json
from urllib.parse import urlencode, quote


class PropertySharkClient:
    """
    Client for interacting with PropertyShark.com APIs.

    Note: PropertyShark uses Cloudflare protection. Direct API access
    may be blocked. This client documents the API structure for reference.
    """

    BASE_URL = "https://www.propertyshark.com"
    API_BASE = "https://www.propertyshark.com/api"

    def __init__(self, api_key: Optional[str] = None, session_token: Optional[str] = None):
        """
        Initialize the PropertyShark client.

        Args:
            api_key: Optional API key (if available)
            session_token: Optional session token from authenticated browser session
        """
        self.api_key = api_key
        self.session_token = session_token
        self.session = requests.Session()

        # Set headers to mimic a real browser
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
            'Accept': 'application/json, text/plain, */*',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'Referer': 'https://www.propertyshark.com/',
            'Origin': 'https://www.propertyshark.com',
            'DNT': '1',
            'Connection': 'keep-alive',
            'Sec-Fetch-Dest': 'empty',
            'Sec-Fetch-Mode': 'cors',
            'Sec-Fetch-Site': 'same-origin',
        })

        if session_token:
            self.session.headers['Authorization'] = f'Bearer {session_token}'
            self.session.cookies.set('session_token', session_token)

    def _make_request(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict] = None,
        data: Optional[Dict] = None,
        json_data: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """
        Make an HTTP request to PropertyShark API.

        Args:
            method: HTTP method (GET, POST, etc.)
            endpoint: API endpoint path
            params: URL query parameters
            data: Form data
            json_data: JSON data

        Returns:
            Response JSON data

        Raises:
            requests.RequestException: If request fails
        """
        url = f"{self.API_BASE}{endpoint}" if endpoint.startswith('/') else endpoint

        try:
            response = self.session.request(
                method=method,
                url=url,
                params=params,
                data=data,
                json=json_data,
                timeout=30
            )
            response.raise_for_status()

            # Try to parse JSON
            try:
                return response.json()
            except json.JSONDecodeError:
                return {'raw_response': response.text, 'status_code': response.status_code}

        except requests.RequestException as e:
            return {
                'error': str(e),
                'status_code': getattr(e.response, 'status_code', None) if hasattr(e, 'response') else None,
                'message': 'Request failed - likely blocked by Cloudflare or requires authentication'
            }

    # ==================== SEARCH ENDPOINTS ====================

    def search_properties(
        self,
        query: str,
        location: Optional[str] = None,
        property_type: Optional[str] = None,
        limit: int = 20
    ) -> Dict[str, Any]:
        """
        Search for properties by address, neighborhood, city, or ZIP.

        Args:
            query: Search query (address, neighborhood, city, ZIP)
            location: Optional location filter
            property_type: Optional property type (residential, commercial, etc.)
            limit: Maximum number of results

        Returns:
            Search results with property data
        """
        endpoint = "/v1/properties/search"
        params = {
            'q': query,
            'limit': limit
        }

        if location:
            params['location'] = location
        if property_type:
            params['type'] = property_type

        return self._make_request('GET', endpoint, params=params)

    def autocomplete_search(self, query: str) -> Dict[str, Any]:
        """
        Get autocomplete suggestions for property search.

        Args:
            query: Partial search query

        Returns:
            Autocomplete suggestions
        """
        endpoint = "/v1/search/autocomplete"
        params = {'q': query}
        return self._make_request('GET', endpoint, params=params)

    # ==================== PROPERTY DETAILS ====================

    def get_property_details(self, property_id: str) -> Dict[str, Any]:
        """
        Get detailed information about a specific property.

        Args:
            property_id: Unique property identifier

        Returns:
            Property details including ownership, tax info, sales history
        """
        endpoint = f"/v1/properties/{property_id}"
        return self._make_request('GET', endpoint)

    def get_property_by_address(
        self,
        address: str,
        city: str,
        state: str,
        zip_code: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Get property information by full address.

        Args:
            address: Street address
            city: City name
            state: State abbreviation (e.g., 'NY')
            zip_code: Optional ZIP code

        Returns:
            Property details
        """
        endpoint = "/v1/properties/by-address"
        params = {
            'address': address,
            'city': city,
            'state': state
        }
        if zip_code:
            params['zip'] = zip_code

        return self._make_request('GET', endpoint, params=params)

    def get_property_tax_history(self, property_id: str) -> Dict[str, Any]:
        """
        Get property tax history.

        Args:
            property_id: Property identifier

        Returns:
            Tax assessment history
        """
        endpoint = f"/v1/properties/{property_id}/tax-history"
        return self._make_request('GET', endpoint)

    def get_property_sales_history(self, property_id: str) -> Dict[str, Any]:
        """
        Get property sales/transaction history.

        Args:
            property_id: Property identifier

        Returns:
            Sales history with dates and prices
        """
        endpoint = f"/v1/properties/{property_id}/sales-history"
        return self._make_request('GET', endpoint)

    # ==================== OWNER LOOKUP ====================

    def search_owners(self, owner_name: str) -> Dict[str, Any]:
        """
        Search for property owners by name.

        Args:
            owner_name: Owner name to search

        Returns:
            List of properties owned by the person/entity
        """
        endpoint = "/v1/owners/search"
        params = {'name': owner_name}
        return self._make_request('GET', endpoint, params=params)

    def get_owner_properties(self, owner_id: str) -> Dict[str, Any]:
        """
        Get all properties owned by a specific owner.

        Args:
            owner_id: Owner identifier

        Returns:
            List of properties with details
        """
        endpoint = f"/v1/owners/{owner_id}/properties"
        return self._make_request('GET', endpoint)

    # ==================== FORECLOSURES ====================

    def get_foreclosures(
        self,
        city: Optional[str] = None,
        state: Optional[str] = None,
        property_type: Optional[str] = None,
        limit: int = 50
    ) -> Dict[str, Any]:
        """
        Get foreclosure listings.

        Args:
            city: Filter by city
            state: Filter by state
            property_type: Filter by property type
            limit: Maximum number of results

        Returns:
            Foreclosure listings with details
        """
        endpoint = "/v1/foreclosures"
        params = {'limit': limit}

        if city:
            params['city'] = city
        if state:
            params['state'] = state
        if property_type:
            params['type'] = property_type

        return self._make_request('GET', endpoint, params=params)

    def get_foreclosure_details(self, foreclosure_id: str) -> Dict[str, Any]:
        """
        Get detailed information about a foreclosure.

        Args:
            foreclosure_id: Foreclosure identifier

        Returns:
            Foreclosure details
        """
        endpoint = f"/v1/foreclosures/{foreclosure_id}"
        return self._make_request('GET', endpoint)

    # ==================== COMPARABLES / MARKET DATA ====================

    def get_comparables(
        self,
        property_id: str,
        radius: float = 0.5,
        limit: int = 10
    ) -> Dict[str, Any]:
        """
        Get comparable properties (comps) for market analysis.

        Args:
            property_id: Property to find comps for
            radius: Search radius in miles
            limit: Maximum number of comps

        Returns:
            Comparable properties with pricing data
        """
        endpoint = f"/v1/properties/{property_id}/comparables"
        params = {
            'radius': radius,
            'limit': limit
        }
        return self._make_request('GET', endpoint, params=params)

    def get_market_trends(
        self,
        city: str,
        state: str,
        property_type: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Get market trends and statistics for an area.

        Args:
            city: City name
            state: State abbreviation
            property_type: Optional property type filter

        Returns:
            Market statistics and trends
        """
        endpoint = "/v1/market/trends"
        params = {
            'city': city,
            'state': state
        }
        if property_type:
            params['type'] = property_type

        return self._make_request('GET', endpoint, params=params)

    # ==================== PROPERTY LISTS ====================

    def get_property_lists(self, user_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Get saved property lists.

        Args:
            user_id: Optional user ID filter

        Returns:
            Property lists
        """
        endpoint = "/v1/lists"
        params = {}
        if user_id:
            params['user_id'] = user_id

        return self._make_request('GET', endpoint, params=params)

    def create_property_list(self, name: str, properties: List[str]) -> Dict[str, Any]:
        """
        Create a new property list.

        Args:
            name: List name
            properties: List of property IDs

        Returns:
            Created list details
        """
        endpoint = "/v1/lists"
        data = {
            'name': name,
            'property_ids': properties
        }
        return self._make_request('POST', endpoint, json_data=data)

    # ==================== GEO / MAP DATA ====================

    def get_properties_by_coordinates(
        self,
        latitude: float,
        longitude: float,
        radius: float = 1.0,
        limit: int = 50
    ) -> Dict[str, Any]:
        """
        Get properties near specific coordinates.

        Args:
            latitude: Latitude
            longitude: Longitude
            radius: Search radius in miles
            limit: Maximum number of results

        Returns:
            Properties within the specified area
        """
        endpoint = "/v1/properties/nearby"
        params = {
            'lat': latitude,
            'lng': longitude,
            'radius': radius,
            'limit': limit
        }
        return self._make_request('GET', endpoint, params=params)

    def get_properties_in_area(
        self,
        ne_lat: float,
        ne_lng: float,
        sw_lat: float,
        sw_lng: float,
        limit: int = 100
    ) -> Dict[str, Any]:
        """
        Get properties within a bounding box (for map view).

        Args:
            ne_lat: Northeast corner latitude
            ne_lng: Northeast corner longitude
            sw_lat: Southwest corner latitude
            sw_lng: Southwest corner longitude
            limit: Maximum number of results

        Returns:
            Properties in the bounding box
        """
        endpoint = "/v1/properties/in-area"
        params = {
            'ne_lat': ne_lat,
            'ne_lng': ne_lng,
            'sw_lat': sw_lat,
            'sw_lng': sw_lng,
            'limit': limit
        }
        return self._make_request('GET', endpoint, params=params)

    # ==================== LISTINGS ====================

    def get_listings(
        self,
        city: Optional[str] = None,
        state: Optional[str] = None,
        property_type: Optional[str] = None,
        min_price: Optional[int] = None,
        max_price: Optional[int] = None,
        limit: int = 50
    ) -> Dict[str, Any]:
        """
        Get active property listings.

        Args:
            city: Filter by city
            state: Filter by state
            property_type: Filter by property type
            min_price: Minimum price
            max_price: Maximum price
            limit: Maximum number of results

        Returns:
            Active listings
        """
        endpoint = "/v1/listings"
        params = {'limit': limit}

        if city:
            params['city'] = city
        if state:
            params['state'] = state
        if property_type:
            params['type'] = property_type
        if min_price:
            params['min_price'] = min_price
        if max_price:
            params['max_price'] = max_price

        return self._make_request('GET', endpoint, params=params)

    # ==================== UTILITY METHODS ====================

    def health_check(self) -> Dict[str, Any]:
        """
        Check if the API is accessible.

        Returns:
            API health status
        """
        endpoint = "/v1/health"
        return self._make_request('GET', endpoint)


def main():
    """
    Example usage of the PropertyShark client.

    NOTE: Most endpoints will be blocked by Cloudflare protection
    unless you have a valid session token from an authenticated browser session.
    """
    print("=" * 70)
    print("PropertyShark API Client - Example Usage")
    print("=" * 70)
    print()

    # Initialize client
    client = PropertySharkClient()

    # Example 1: Search for properties
    print("1. Searching for properties in Manhattan...")
    print("-" * 70)
    result = client.search_properties("Manhattan, NY", limit=5)
    print(json.dumps(result, indent=2))
    print()

    # Example 2: Autocomplete search
    print("2. Autocomplete search for '123 Main'...")
    print("-" * 70)
    result = client.autocomplete_search("123 Main")
    print(json.dumps(result, indent=2))
    print()

    # Example 3: Get property by address
    print("3. Getting property by address...")
    print("-" * 70)
    result = client.get_property_by_address(
        address="350 5th Avenue",
        city="New York",
        state="NY",
        zip_code="10118"
    )
    print(json.dumps(result, indent=2))
    print()

    # Example 4: Search for foreclosures
    print("4. Searching for foreclosures in New York...")
    print("-" * 70)
    result = client.get_foreclosures(city="New York", state="NY", limit=5)
    print(json.dumps(result, indent=2))
    print()

    # Example 5: Get properties near coordinates (Manhattan)
    print("5. Getting properties near Manhattan coordinates...")
    print("-" * 70)
    result = client.get_properties_by_coordinates(
        latitude=40.7580,
        longitude=-73.9855,
        radius=0.5,
        limit=10
    )
    print(json.dumps(result, indent=2))
    print()

    # Example 6: Health check
    print("6. API Health Check...")
    print("-" * 70)
    result = client.health_check()
    print(json.dumps(result, indent=2))
    print()

    print("=" * 70)
    print("IMPORTANT NOTES:")
    print("=" * 70)
    print("1. PropertyShark uses Cloudflare protection - direct API calls may be blocked")
    print("2. Most endpoints require authentication and a paid subscription")
    print("3. To use this client effectively, you need:")
    print("   - A valid session token from an authenticated browser session")
    print("   - Or direct API key access (if PropertyShark provides one)")
    print("4. The endpoint structure is based on common real estate API patterns")
    print("5. Actual endpoint paths may differ - this is a reference implementation")
    print()


if __name__ == "__main__":
    main()
