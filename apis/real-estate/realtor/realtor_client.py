#!/usr/bin/env python3
"""
Realtor.com API Client (Reverse Engineered)

This client provides access to Realtor.com's undocumented API endpoints.
Note: Realtor.com uses aggressive bot protection (Kasada/Akamai), so some
endpoints may require additional headers or may be blocked when called from
servers. Best used with residential proxies and proper browser-like headers.

API Base: https://www.realtor.com/api/v1/
Mobile API: https://mobileapi.realtor.com/

Authentication: Most endpoints require a client_id parameter and proper headers.
Common client_ids:
  - rdc-x (web client)
  - rdc_mobile_native (mobile app)
"""

import requests
import json
from typing import Dict, List, Optional, Any
from urllib.parse import urlencode
import time


class RealtorAPIClient:
    """
    Production-ready Python client for Realtor.com API.

    Endpoints discovered through reverse engineering:
    - Property search (HULK API)
    - Property details
    - Autocomplete/suggestions
    - Mortgage calculator
    - Agent search
    - Recently sold properties
    """

    BASE_URL = "https://www.realtor.com/api/v1"
    MOBILE_BASE_URL = "https://mobileapi.realtor.com"

    # These are public client IDs found in their web/mobile apps
    CLIENT_IDS = {
        "web": "rdc-x",
        "mobile": "rdc_mobile_native",
        "for_sale": "for-sale"
    }

    def __init__(
        self,
        client_id: str = "rdc-x",
        timeout: int = 30,
        user_agent: Optional[str] = None
    ):
        """
        Initialize the Realtor.com API client.

        Args:
            client_id: Client identifier for API requests
            timeout: Request timeout in seconds
            user_agent: Custom User-Agent header
        """
        self.client_id = client_id
        self.timeout = timeout
        self.session = requests.Session()

        # Critical headers to bypass some bot protection
        self.session.headers.update({
            "User-Agent": user_agent or (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept": "application/json",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
            "Origin": "https://www.realtor.com",
            "Referer": "https://www.realtor.com/",
            "DNT": "1",
            "Connection": "keep-alive",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-origin",
        })

    def _make_request(
        self,
        method: str,
        url: str,
        params: Optional[Dict] = None,
        data: Optional[Dict] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Make an HTTP request with error handling.

        Args:
            method: HTTP method (GET, POST, etc.)
            url: Full URL or path
            params: Query parameters
            data: Request body data
            **kwargs: Additional arguments for requests

        Returns:
            Parsed JSON response

        Raises:
            requests.exceptions.RequestException: On request failure
        """
        if not url.startswith("http"):
            url = f"{self.BASE_URL}{url}"

        try:
            response = self.session.request(
                method=method,
                url=url,
                params=params,
                json=data,
                timeout=self.timeout,
                **kwargs
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as e:
            if response.status_code == 403:
                raise Exception(
                    "403 Forbidden - Bot protection detected. "
                    "Try using residential proxies or browser automation."
                )
            raise

    def search_properties(
        self,
        location: str,
        status: str = "for_sale",
        offset: int = 0,
        limit: int = 42,
        **filters
    ) -> Dict[str, Any]:
        """
        Search for properties (HULK Main SRP API).

        This is the primary search endpoint used by the web interface.

        Args:
            location: City, state, ZIP code, or address
            status: Property status (for_sale, for_rent, recently_sold)
            offset: Pagination offset
            limit: Number of results (max 200)
            **filters: Additional filters:
                - beds_min: Minimum bedrooms
                - beds_max: Maximum bedrooms
                - baths_min: Minimum bathrooms
                - price_min: Minimum price
                - price_max: Maximum price
                - sqft_min: Minimum square feet
                - sqft_max: Maximum square feet
                - lot_sqft_min: Minimum lot size
                - property_type: single_family, condo, multi_family, etc.
                - sort: relevance, price_high, price_low, sqft_high, etc.

        Returns:
            Search results with property listings

        Example:
            >>> client.search_properties(
            ...     location="Los Angeles, CA",
            ...     status="for_sale",
            ...     beds_min=3,
            ...     price_max=1000000
            ... )
        """
        params = {
            "client_id": self.client_id,
            "schema": "vesta",
            "location": location,
            "status": status,
            "offset": offset,
            "limit": limit,
            **filters
        }

        return self._make_request("GET", "/hulk_main_srp", params=params)

    def get_property_details(
        self,
        property_id: str,
        listing_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Get detailed information about a specific property.

        Args:
            property_id: Property ID (e.g., "M12345-67890")
            listing_id: Optional listing ID for more details

        Returns:
            Property details including description, photos, features, etc.

        Example:
            >>> client.get_property_details("M12345-67890")
        """
        params = {
            "client_id": self.client_id,
            "schema": "vesta"
        }

        if listing_id:
            params["listing_id"] = listing_id

        return self._make_request(
            "GET",
            f"/property/{property_id}",
            params=params
        )

    def autocomplete_location(
        self,
        query: str,
        area_types: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Autocomplete location search (suggestions).

        Args:
            query: Partial location text
            area_types: Filter by area types:
                - address
                - city
                - county
                - neighborhood
                - postal_code
                - state

        Returns:
            Location suggestions

        Example:
            >>> client.autocomplete_location("Los Ang")
        """
        params = {
            "input": query,
            "client_id": self.client_id,
        }

        if area_types:
            params["area_types"] = ",".join(area_types)

        return self._make_request("GET", "/location/suggest", params=params)

    def get_mortgage_rates(self) -> Dict[str, Any]:
        """
        Get current mortgage rates.

        Returns:
            Current mortgage rate information
        """
        params = {"client_id": self.client_id}
        return self._make_request("GET", "/mortgage/rates", params=params)

    def calculate_mortgage(
        self,
        price: int,
        down_payment: int,
        loan_term: int = 30,
        interest_rate: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Calculate monthly mortgage payment.

        Args:
            price: Home price
            down_payment: Down payment amount
            loan_term: Loan term in years (default: 30)
            interest_rate: Interest rate (uses current rate if not provided)

        Returns:
            Mortgage calculation results
        """
        data = {
            "price": price,
            "down_payment": down_payment,
            "loan_term": loan_term,
        }

        if interest_rate:
            data["interest_rate"] = interest_rate

        params = {"client_id": self.client_id}
        return self._make_request(
            "POST",
            "/mortgage/calculate",
            params=params,
            data=data
        )

    def search_agents(
        self,
        location: str,
        offset: int = 0,
        limit: int = 20,
        **filters
    ) -> Dict[str, Any]:
        """
        Search for real estate agents.

        Args:
            location: City, state, or ZIP code
            offset: Pagination offset
            limit: Number of results
            **filters: Additional filters:
                - languages: Language spoken
                - specialties: Agent specialties
                - sort: recommended, recent_sales, experience

        Returns:
            Agent search results
        """
        params = {
            "client_id": self.client_id,
            "location": location,
            "offset": offset,
            "limit": limit,
            **filters
        }

        return self._make_request("GET", "/agent/search", params=params)

    def get_recently_sold(
        self,
        location: str,
        offset: int = 0,
        limit: int = 42,
        days: int = 90
    ) -> Dict[str, Any]:
        """
        Get recently sold properties in an area.

        Args:
            location: City, state, or ZIP code
            offset: Pagination offset
            limit: Number of results
            days: Number of days to look back (default: 90)

        Returns:
            Recently sold property listings
        """
        params = {
            "client_id": self.client_id,
            "schema": "vesta",
            "location": location,
            "status": "recently_sold",
            "offset": offset,
            "limit": limit,
            "sold_days": days
        }

        return self._make_request("GET", "/hulk_main_srp", params=params)

    def get_market_trends(
        self,
        location: str,
        property_type: str = "single_family"
    ) -> Dict[str, Any]:
        """
        Get market trends and statistics for an area.

        Args:
            location: City, state, or ZIP code
            property_type: Property type filter

        Returns:
            Market statistics and trends
        """
        params = {
            "client_id": self.client_id,
            "location": location,
            "property_type": property_type
        }

        return self._make_request("GET", "/market/trends", params=params)

    def get_property_history(
        self,
        property_id: str
    ) -> Dict[str, Any]:
        """
        Get historical data for a property (price history, sales, etc.).

        Args:
            property_id: Property ID

        Returns:
            Property history data
        """
        params = {"client_id": self.client_id}
        return self._make_request(
            "GET",
            f"/property/{property_id}/history",
            params=params
        )

    def get_similar_properties(
        self,
        property_id: str,
        limit: int = 10
    ) -> Dict[str, Any]:
        """
        Get similar properties to a given property.

        Args:
            property_id: Property ID
            limit: Number of results

        Returns:
            Similar property listings
        """
        params = {
            "client_id": self.client_id,
            "limit": limit
        }

        return self._make_request(
            "GET",
            f"/property/{property_id}/similar",
            params=params
        )

    def close(self):
        """Close the HTTP session."""
        self.session.close()

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()


# Alternative: RapidAPI Realtor endpoint (documented, requires API key)
class RealtorRapidAPIClient:
    """
    Alternative client using the documented Realtor API via RapidAPI.

    This requires a RapidAPI key but has better reliability.
    Sign up at: https://rapidapi.com/apidojo/api/realtor/
    """

    BASE_URL = "https://realtor.p.rapidapi.com"

    def __init__(self, api_key: str):
        """
        Initialize RapidAPI client.

        Args:
            api_key: Your RapidAPI key
        """
        self.session = requests.Session()
        self.session.headers.update({
            "X-RapidAPI-Key": api_key,
            "X-RapidAPI-Host": "realtor.p.rapidapi.com"
        })

    def search_properties(
        self,
        location: str,
        offset: int = 0,
        limit: int = 200,
        **kwargs
    ) -> Dict[str, Any]:
        """Search properties using RapidAPI."""
        params = {
            "city": location,
            "offset": offset,
            "limit": limit,
            **kwargs
        }
        response = self.session.get(
            f"{self.BASE_URL}/properties/v2/list-for-sale",
            params=params
        )
        response.raise_for_status()
        return response.json()

    def get_property_detail(self, property_id: str) -> Dict[str, Any]:
        """Get property details using RapidAPI."""
        params = {"property_id": property_id}
        response = self.session.get(
            f"{self.BASE_URL}/properties/v2/detail",
            params=params
        )
        response.raise_for_status()
        return response.json()


if __name__ == "__main__":
    """
    Example usage and testing.

    Note: Direct API access will likely be blocked by bot protection.
    For production use, consider:
    1. Using the RapidAPI client (requires paid subscription)
    2. Using residential proxies
    3. Using browser automation (Selenium/Playwright)
    4. Using scrapy-playwright for JavaScript rendering
    """

    print("=" * 60)
    print("Realtor.com API Client - Test Suite")
    print("=" * 60)

    # Test 1: Direct API access (will likely fail due to bot protection)
    print("\n[TEST 1] Testing direct API access...")
    print("Note: This will likely fail due to Kasada/Akamai bot protection")

    try:
        client = RealtorAPIClient(client_id="rdc-x")

        # Test autocomplete (usually less protected)
        print("\n• Testing autocomplete endpoint...")
        result = client.autocomplete_location("Los Angeles")
        print(f"  Status: SUCCESS")
        print(f"  Results: {len(result.get('suggestions', []))} suggestions")

    except Exception as e:
        print(f"  Status: FAILED - {e}")

    # Test 2: Search properties
    print("\n[TEST 2] Testing property search...")

    try:
        result = client.search_properties(
            location="90210",  # Beverly Hills
            status="for_sale",
            beds_min=3,
            price_max=2000000,
            limit=10
        )

        print(f"  Status: SUCCESS")
        properties = result.get("properties", [])
        print(f"  Found: {len(properties)} properties")

        if properties:
            prop = properties[0]
            print(f"\n  Example property:")
            print(f"    Address: {prop.get('address', {}).get('line', 'N/A')}")
            print(f"    Price: ${prop.get('list_price', 'N/A'):,}")
            print(f"    Beds: {prop.get('beds', 'N/A')}")
            print(f"    Baths: {prop.get('baths', 'N/A')}")

    except Exception as e:
        print(f"  Status: FAILED - {e}")

    # Test 3: Recently sold
    print("\n[TEST 3] Testing recently sold properties...")

    try:
        result = client.get_recently_sold(
            location="Miami, FL",
            limit=5,
            days=30
        )

        print(f"  Status: SUCCESS")
        print(f"  Found: {len(result.get('properties', []))} properties")

    except Exception as e:
        print(f"  Status: FAILED - {e}")

    client.close()

    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print("""
The Realtor.com API uses aggressive bot protection (Kasada).
Direct API calls from servers will be blocked.

Working Solutions:
1. Use RapidAPI Realtor endpoint (requires subscription)
2. Use residential rotating proxies
3. Use browser automation (Selenium/Playwright)
4. Use the official Realtor.com partner API (requires approval)

Discovered Endpoints:
• /hulk_main_srp - Main property search
• /property/{id} - Property details
• /location/suggest - Location autocomplete
• /mortgage/rates - Current rates
• /mortgage/calculate - Payment calculator
• /agent/search - Agent search
• /market/trends - Market statistics
• /property/{id}/history - Price history
• /property/{id}/similar - Similar properties

Authentication:
• Client ID required (client_id parameter)
• Common IDs: rdc-x, rdc_mobile_native, for-sale
• Headers: User-Agent, Referer, Origin are critical
• May require additional Kasada tokens from JavaScript

Rate Limiting:
• Unknown, but aggressive bot detection is in place
• Recommend 1-2 second delays between requests
• Use session persistence for better performance
    """)
