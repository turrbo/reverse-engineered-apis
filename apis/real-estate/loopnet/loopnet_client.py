#!/usr/bin/env python3
"""
LoopNet.com Unofficial API Client
==================================

DISCLAIMER: This client is based on reverse-engineering research of LoopNet.com.
LoopNet employs aggressive bot protection (Akamai) that blocks most automated access.

This client demonstrates the API structure and patterns, but direct usage will be
blocked without proper browser automation, CAPTCHA solving, or residential proxies.

WARNING: Scraping LoopNet may violate their Terms of Service. Use at your own risk.
This is for educational purposes only.

Author: Generated via API reverse engineering
License: MIT
"""

import requests
from typing import Dict, List, Optional, Any, Union
from urllib.parse import urljoin, urlencode
import json
import time
from dataclasses import dataclass
from enum import Enum


class PropertyType(Enum):
    """Commercial property types on LoopNet."""
    OFFICE = "office"
    RETAIL = "retail"
    INDUSTRIAL = "industrial"
    LAND = "land"
    MULTIFAMILY = "multifamily"
    FLEX = "flex"
    COWORKING = "coworking"
    MIXED_USE = "mixed-use"
    HOSPITALITY = "hospitality"
    HEALTHCARE = "healthcare"
    SPECIALTY = "specialty"


class ListingType(Enum):
    """Type of listing."""
    FOR_SALE = "for-sale"
    FOR_LEASE = "for-lease"
    AUCTION = "auction"


@dataclass
class SearchFilters:
    """Filters for property search."""
    location: Optional[str] = None
    property_type: Optional[PropertyType] = None
    listing_type: Optional[ListingType] = ListingType.FOR_SALE
    min_price: Optional[int] = None
    max_price: Optional[int] = None
    min_size: Optional[int] = None  # Square feet
    max_size: Optional[int] = None  # Square feet
    page: int = 1
    per_page: int = 25
    sort_by: str = "relevance"  # relevance, price, size, date


class LoopNetClient:
    """
    Unofficial LoopNet API Client.

    IMPORTANT: LoopNet uses Akamai bot protection. Most requests will return 403.
    This client requires:
    - Browser automation (Selenium/Playwright with stealth plugins)
    - CAPTCHA solving service
    - Residential proxies with session persistence
    - Cookie/session token extraction from authenticated browser

    This implementation shows the API structure for educational purposes.
    """

    BASE_URL = "https://www.loopnet.com"
    API_BASE = "https://www.loopnet.com/api"

    # Alternative API endpoints (may be used internally)
    SEARCH_API = "https://search.loopnet.com/api"
    GRAPHQL_API = "https://www.loopnet.com/graphql"

    def __init__(
        self,
        session_cookies: Optional[Dict[str, str]] = None,
        user_agent: Optional[str] = None,
        proxy: Optional[str] = None,
        timeout: int = 30
    ):
        """
        Initialize LoopNet client.

        Args:
            session_cookies: Cookies from authenticated browser session (if available)
            user_agent: Custom user agent string
            proxy: Proxy URL (format: http://user:pass@host:port)
            timeout: Request timeout in seconds
        """
        self.session = requests.Session()
        self.timeout = timeout

        # Set realistic headers to mimic browser
        self.session.headers.update({
            "User-Agent": user_agent or (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
            "Referer": "https://www.loopnet.com/",
            "Origin": "https://www.loopnet.com",
            "DNT": "1",
            "Connection": "keep-alive",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-origin",
            "Sec-Ch-Ua": '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
            "Sec-Ch-Ua-Mobile": "?0",
            "Sec-Ch-Ua-Platform": '"Windows"',
        })

        if session_cookies:
            self.session.cookies.update(session_cookies)

        if proxy:
            self.session.proxies.update({
                "http": proxy,
                "https": proxy
            })

    def _make_request(
        self,
        method: str,
        url: str,
        **kwargs
    ) -> requests.Response:
        """
        Make HTTP request with error handling.

        Args:
            method: HTTP method
            url: Request URL
            **kwargs: Additional arguments for requests

        Returns:
            Response object

        Raises:
            requests.HTTPError: On HTTP errors
        """
        try:
            response = self.session.request(
                method,
                url,
                timeout=self.timeout,
                **kwargs
            )

            # Check for bot protection
            if response.status_code == 403:
                if "edgesuite.net" in response.text or "Access Denied" in response.text:
                    raise RuntimeError(
                        "Blocked by Akamai bot protection. "
                        "This requires browser automation with stealth mode."
                    )

            response.raise_for_status()
            return response

        except requests.RequestException as e:
            print(f"Request failed: {e}")
            raise

    def search_properties(
        self,
        filters: SearchFilters
    ) -> Dict[str, Any]:
        """
        Search for commercial properties.

        This endpoint is typically at /api/search or uses GraphQL.
        Exact endpoint structure requires browser inspection.

        Args:
            filters: Search filter parameters

        Returns:
            Dictionary with search results

        Note:
            This will likely return 403 without proper authentication/cookies
        """
        # Build query parameters
        params = {
            "page": filters.page,
            "per_page": filters.per_page,
            "sort": filters.sort_by
        }

        if filters.location:
            params["location"] = filters.location

        if filters.property_type:
            params["property_type"] = filters.property_type.value

        if filters.listing_type:
            params["listing_type"] = filters.listing_type.value

        if filters.min_price:
            params["min_price"] = filters.min_price

        if filters.max_price:
            params["max_price"] = filters.max_price

        if filters.min_size:
            params["min_size"] = filters.min_size

        if filters.max_size:
            params["max_size"] = filters.max_size

        # Try multiple potential endpoints
        potential_urls = [
            f"{self.API_BASE}/search",
            f"{self.API_BASE}/v1/search",
            f"{self.API_BASE}/v2/search",
            f"{self.SEARCH_API}/search",
            f"{self.API_BASE}/properties/search"
        ]

        for url in potential_urls:
            try:
                response = self._make_request("GET", url, params=params)
                return response.json()
            except Exception as e:
                print(f"Failed endpoint {url}: {e}")
                continue

        raise RuntimeError("All search endpoints failed. Bot protection active.")

    def get_property_details(self, property_id: str) -> Dict[str, Any]:
        """
        Get detailed information about a specific property.

        Args:
            property_id: LoopNet property ID

        Returns:
            Dictionary with property details
        """
        potential_urls = [
            f"{self.API_BASE}/property/{property_id}",
            f"{self.API_BASE}/v1/property/{property_id}",
            f"{self.API_BASE}/properties/{property_id}",
            f"{self.API_BASE}/listing/{property_id}"
        ]

        for url in potential_urls:
            try:
                response = self._make_request("GET", url)
                return response.json()
            except Exception as e:
                print(f"Failed endpoint {url}: {e}")
                continue

        raise RuntimeError(f"Could not fetch property {property_id}")

    def autocomplete_location(self, query: str) -> List[Dict[str, Any]]:
        """
        Get location autocomplete suggestions.

        Args:
            query: Partial location text (e.g., "New York")

        Returns:
            List of location suggestions
        """
        potential_urls = [
            f"{self.API_BASE}/autocomplete",
            f"{self.API_BASE}/location/autocomplete",
            f"{self.API_BASE}/v1/autocomplete",
            f"{self.API_BASE}/suggest/location"
        ]

        params = {"q": query, "type": "location"}

        for url in potential_urls:
            try:
                response = self._make_request("GET", url, params=params)
                return response.json()
            except Exception as e:
                print(f"Failed endpoint {url}: {e}")
                continue

        return []

    def get_featured_listings(self, count: int = 10) -> List[Dict[str, Any]]:
        """
        Get featured property listings.

        Args:
            count: Number of listings to return

        Returns:
            List of featured properties
        """
        url = f"{self.API_BASE}/featured"
        params = {"count": count}

        try:
            response = self._make_request("GET", url, params=params)
            return response.json()
        except Exception as e:
            print(f"Failed to get featured listings: {e}")
            return []

    def search_by_coordinates(
        self,
        latitude: float,
        longitude: float,
        radius_miles: float = 5.0,
        property_type: Optional[PropertyType] = None
    ) -> Dict[str, Any]:
        """
        Search properties by geographic coordinates.

        Args:
            latitude: Latitude coordinate
            longitude: Longitude coordinate
            radius_miles: Search radius in miles
            property_type: Optional property type filter

        Returns:
            Dictionary with nearby properties
        """
        params = {
            "lat": latitude,
            "lon": longitude,
            "radius": radius_miles
        }

        if property_type:
            params["property_type"] = property_type.value

        url = f"{self.API_BASE}/search/nearby"

        try:
            response = self._make_request("GET", url, params=params)
            return response.json()
        except Exception as e:
            print(f"Coordinate search failed: {e}")
            raise

    def get_market_statistics(self, location: str) -> Dict[str, Any]:
        """
        Get market statistics for a location.

        Args:
            location: Location name or ID

        Returns:
            Market statistics data
        """
        url = f"{self.API_BASE}/market/stats"
        params = {"location": location}

        try:
            response = self._make_request("GET", url, params=params)
            return response.json()
        except Exception as e:
            print(f"Market stats request failed: {e}")
            return {}

    def graphql_query(self, query: str, variables: Optional[Dict] = None) -> Dict[str, Any]:
        """
        Execute GraphQL query (if LoopNet uses GraphQL).

        Args:
            query: GraphQL query string
            variables: Query variables

        Returns:
            GraphQL response data
        """
        payload = {
            "query": query,
            "variables": variables or {}
        }

        try:
            response = self._make_request(
                "POST",
                self.GRAPHQL_API,
                json=payload
            )
            return response.json()
        except Exception as e:
            print(f"GraphQL query failed: {e}")
            raise

    def close(self):
        """Close the session."""
        self.session.close()


# Example usage and testing
if __name__ == "__main__":
    print("=" * 80)
    print("LoopNet Unofficial API Client - Test Suite")
    print("=" * 80)
    print()
    print("WARNING: LoopNet uses Akamai bot protection.")
    print("Most requests will fail with 403 Forbidden without:")
    print("  - Browser automation (Selenium/Playwright with stealth)")
    print("  - Valid session cookies from authenticated browser")
    print("  - Residential proxies")
    print("  - CAPTCHA solving")
    print()
    print("=" * 80)
    print()

    # Initialize client
    client = LoopNetClient()

    # Test 1: Simple property search
    print("Test 1: Searching for office properties in New York...")
    print("-" * 80)

    search_filters = SearchFilters(
        location="New York, NY",
        property_type=PropertyType.OFFICE,
        listing_type=ListingType.FOR_SALE,
        min_price=1000000,
        max_price=10000000,
        page=1,
        per_page=10
    )

    try:
        results = client.search_properties(search_filters)
        print(f"✓ Search successful! Found {len(results.get('results', []))} properties")
        print(json.dumps(results, indent=2)[:500] + "...")
    except Exception as e:
        print(f"✗ Search failed: {e}")

    print()

    # Test 2: Location autocomplete
    print("Test 2: Testing location autocomplete...")
    print("-" * 80)

    try:
        suggestions = client.autocomplete_location("Los Angeles")
        print(f"✓ Autocomplete successful! Got {len(suggestions)} suggestions")
        for i, suggestion in enumerate(suggestions[:5], 1):
            print(f"  {i}. {suggestion.get('name', 'N/A')}")
    except Exception as e:
        print(f"✗ Autocomplete failed: {e}")

    print()

    # Test 3: Get property details
    print("Test 3: Getting property details...")
    print("-" * 80)

    try:
        # Example property ID (likely doesn't exist)
        details = client.get_property_details("12345678")
        print(f"✓ Property details retrieved!")
        print(json.dumps(details, indent=2)[:500] + "...")
    except Exception as e:
        print(f"✗ Property details failed: {e}")

    print()

    # Test 4: Coordinate search
    print("Test 4: Searching by coordinates (Manhattan)...")
    print("-" * 80)

    try:
        # Manhattan coordinates
        nearby = client.search_by_coordinates(
            latitude=40.7589,
            longitude=-73.9851,
            radius_miles=2.0,
            property_type=PropertyType.RETAIL
        )
        print(f"✓ Coordinate search successful!")
        print(json.dumps(nearby, indent=2)[:500] + "...")
    except Exception as e:
        print(f"✗ Coordinate search failed: {e}")

    print()

    # Test 5: Featured listings
    print("Test 5: Getting featured listings...")
    print("-" * 80)

    try:
        featured = client.get_featured_listings(count=5)
        print(f"✓ Featured listings retrieved! Got {len(featured)} listings")
    except Exception as e:
        print(f"✗ Featured listings failed: {e}")

    print()

    # Test 6: Market statistics
    print("Test 6: Getting market statistics...")
    print("-" * 80)

    try:
        stats = client.get_market_statistics("New York, NY")
        print(f"✓ Market statistics retrieved!")
        print(json.dumps(stats, indent=2)[:500] + "...")
    except Exception as e:
        print(f"✗ Market statistics failed: {e}")

    print()
    print("=" * 80)
    print("Test suite completed!")
    print()
    print("NEXT STEPS:")
    print("  1. Use browser automation (Selenium/Playwright) to bypass bot protection")
    print("  2. Extract cookies from authenticated browser session")
    print("  3. Use residential proxies to avoid IP bans")
    print("  4. Implement CAPTCHA solving integration")
    print("  5. Add rate limiting and request throttling")
    print("  6. Inspect actual API endpoints using browser DevTools Network tab")
    print("=" * 80)

    # Clean up
    client.close()
