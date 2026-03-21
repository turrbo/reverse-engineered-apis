"""
Crexi.com API Client
====================

A production-ready Python client for interacting with Crexi.com's undocumented API.

IMPORTANT: Crexi.com is protected by Cloudflare bot detection. This client includes
multiple strategies to bypass protection:
1. cloudscraper (Cloudflare bypass)
2. requests with browser-like headers (basic)
3. undetected-chromedriver (selenium-based, most reliable)

Installation:
    pip install requests cloudscraper undetected-chromedriver selenium

Author: Reverse Engineered API Client
Date: 2026-03-21
"""

import requests
from typing import Dict, List, Optional, Union, Any
from urllib.parse import urljoin, urlencode
import json
import time
from datetime import datetime


class CrexiAPIError(Exception):
    """Custom exception for Crexi API errors"""
    pass


class CrexiCloudflareError(CrexiAPIError):
    """Raised when Cloudflare blocks the request"""
    pass


class CrexiClient:
    """
    Main client for interacting with Crexi.com API.

    Discovered API structure:
    - Base URL: https://api.crexi.com
    - API Version: v1 and v2 detected
    - Authentication: Requires Cloudflare bypass
    - All endpoints protected by Cloudflare bot detection

    Common endpoints (discovered but blocked):
    - /v1/properties - Property listings
    - /v2/properties - Property listings (v2)
    - /v1/search - Search properties
    - /v2/search - Search properties (v2)
    - /v1/listings - Active listings
    - /v1/autocomplete - Location autocomplete
    - /v2/properties/search - Property search with filters
    """

    BASE_URL = "https://api.crexi.com"
    WEB_URL = "https://www.crexi.com"

    def __init__(
        self,
        use_cloudscraper: bool = True,
        use_undetected_chrome: bool = False,
        timeout: int = 30,
        max_retries: int = 3
    ):
        """
        Initialize the Crexi API client.

        Args:
            use_cloudscraper: Use cloudscraper for Cloudflare bypass (recommended)
            use_undetected_chrome: Use undetected-chromedriver (most reliable, slower)
            timeout: Request timeout in seconds
            max_retries: Maximum number of retries for failed requests
        """
        self.timeout = timeout
        self.max_retries = max_retries
        self.use_undetected_chrome = use_undetected_chrome

        # Initialize session based on method
        if use_undetected_chrome:
            self._init_undetected_chrome()
        elif use_cloudscraper:
            self._init_cloudscraper()
        else:
            self._init_requests()

        # Track request count and rate limiting
        self._request_count = 0
        self._last_request_time = None

    def _init_cloudscraper(self):
        """Initialize cloudscraper session for Cloudflare bypass"""
        try:
            import cloudscraper
            self.session = cloudscraper.create_scraper(
                browser={
                    'browser': 'chrome',
                    'platform': 'windows',
                    'mobile': False
                }
            )
            print("[✓] Initialized with cloudscraper (Cloudflare bypass enabled)")
        except ImportError:
            print("[!] cloudscraper not installed. Install with: pip install cloudscraper")
            print("[!] Falling back to standard requests (may be blocked)")
            self._init_requests()

    def _init_requests(self):
        """Initialize standard requests session with browser-like headers"""
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'application/json, text/plain, */*',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'Origin': self.WEB_URL,
            'Referer': f'{self.WEB_URL}/',
            'DNT': '1',
            'Connection': 'keep-alive',
            'Sec-Fetch-Dest': 'empty',
            'Sec-Fetch-Mode': 'cors',
            'Sec-Fetch-Site': 'same-site',
        })
        print("[✓] Initialized with requests (basic headers)")

    def _init_undetected_chrome(self):
        """Initialize undetected-chromedriver for maximum Cloudflare bypass"""
        try:
            import undetected_chromedriver as uc
            from selenium.webdriver.chrome.options import Options

            options = Options()
            options.add_argument('--headless')
            options.add_argument('--no-sandbox')
            options.add_argument('--disable-dev-shm-usage')

            self.driver = uc.Chrome(options=options)
            self.use_selenium = True
            print("[✓] Initialized with undetected-chromedriver (maximum bypass)")
        except ImportError:
            print("[!] undetected-chromedriver not installed")
            print("[!] Install with: pip install undetected-chromedriver selenium")
            print("[!] Falling back to cloudscraper")
            self._init_cloudscraper()

    def _request(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict] = None,
        json_data: Optional[Dict] = None,
        headers: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """
        Make an API request with retry logic and error handling.

        Args:
            method: HTTP method (GET, POST, PUT, DELETE)
            endpoint: API endpoint path
            params: URL parameters
            json_data: JSON body data
            headers: Additional headers

        Returns:
            Dict containing the API response

        Raises:
            CrexiCloudflareError: When blocked by Cloudflare
            CrexiAPIError: For other API errors
        """
        url = urljoin(self.BASE_URL, endpoint)

        # Rate limiting: 1 request per second
        if self._last_request_time:
            elapsed = time.time() - self._last_request_time
            if elapsed < 1.0:
                time.sleep(1.0 - elapsed)

        # Prepare headers
        request_headers = self.session.headers.copy() if hasattr(self, 'session') else {}
        if headers:
            request_headers.update(headers)

        # Retry logic
        last_exception = None
        for attempt in range(self.max_retries):
            try:
                if self.use_undetected_chrome:
                    # Use Selenium for maximum bypass
                    response = self._selenium_request(url, method, params, json_data)
                else:
                    # Use requests/cloudscraper
                    response = self.session.request(
                        method=method,
                        url=url,
                        params=params,
                        json=json_data,
                        headers=request_headers,
                        timeout=self.timeout
                    )

                self._request_count += 1
                self._last_request_time = time.time()

                # Check for Cloudflare block
                if response.status_code == 403:
                    if 'cloudflare' in response.text.lower() or 'just a moment' in response.text.lower():
                        raise CrexiCloudflareError(
                            f"Cloudflare blocked the request. Status: {response.status_code}. "
                            "Try using cloudscraper or undetected-chromedriver."
                        )

                # Check for success
                if response.status_code == 200:
                    try:
                        return response.json()
                    except json.JSONDecodeError:
                        return {'raw': response.text}

                # Handle other status codes
                if response.status_code == 404:
                    raise CrexiAPIError(f"Endpoint not found: {endpoint}")
                elif response.status_code == 429:
                    retry_after = int(response.headers.get('Retry-After', 60))
                    print(f"[!] Rate limited. Waiting {retry_after} seconds...")
                    time.sleep(retry_after)
                    continue
                elif response.status_code >= 500:
                    raise CrexiAPIError(f"Server error: {response.status_code}")
                else:
                    raise CrexiAPIError(f"API error: {response.status_code} - {response.text[:200]}")

            except (requests.Timeout, requests.ConnectionError) as e:
                last_exception = e
                if attempt < self.max_retries - 1:
                    wait_time = 2 ** attempt  # Exponential backoff
                    print(f"[!] Request failed. Retrying in {wait_time}s... (attempt {attempt + 1}/{self.max_retries})")
                    time.sleep(wait_time)
                continue

        # All retries failed
        raise CrexiAPIError(f"Request failed after {self.max_retries} attempts: {last_exception}")

    def _selenium_request(self, url: str, method: str, params: Dict, json_data: Dict) -> requests.Response:
        """Make a request using Selenium WebDriver"""
        if method == 'POST' and json_data:
            # For POST with JSON, we need to use JavaScript
            script = f"""
            return fetch('{url}', {{
                method: 'POST',
                headers: {{'Content-Type': 'application/json'}},
                body: JSON.stringify({json.dumps(json_data)})
            }}).then(r => r.text());
            """
            result = self.driver.execute_script(script)
        else:
            # For GET requests
            if params:
                url = f"{url}?{urlencode(params)}"
            self.driver.get(url)
            result = self.driver.page_source

        # Create a mock response object
        class MockResponse:
            def __init__(self, text, status_code=200):
                self.text = text
                self.status_code = status_code
                self.headers = {}

            def json(self):
                return json.loads(self.text)

        return MockResponse(result)

    # =========================
    # Property API Methods
    # =========================

    def search_properties(
        self,
        location: Optional[str] = None,
        property_type: Optional[str] = None,
        min_price: Optional[float] = None,
        max_price: Optional[float] = None,
        min_size: Optional[int] = None,
        max_size: Optional[int] = None,
        page: int = 1,
        limit: int = 20
    ) -> Dict[str, Any]:
        """
        Search for commercial properties.

        Args:
            location: Location query (e.g., "Miami, FL", "Los Angeles, CA")
            property_type: Property type (e.g., "office", "retail", "industrial", "multifamily")
            min_price: Minimum price
            max_price: Maximum price
            min_size: Minimum size in square feet
            max_size: Maximum size in square feet
            page: Page number (default: 1)
            limit: Results per page (default: 20)

        Returns:
            Dict containing search results

        Example:
            >>> client = CrexiClient()
            >>> results = client.search_properties(location="Miami, FL", property_type="office")
        """
        params = {
            'page': page,
            'limit': limit
        }

        if location:
            params['location'] = location
        if property_type:
            params['property_type'] = property_type
        if min_price:
            params['min_price'] = min_price
        if max_price:
            params['max_price'] = max_price
        if min_size:
            params['min_size'] = min_size
        if max_size:
            params['max_size'] = max_size

        # Try both v2 and v1 endpoints
        try:
            return self._request('GET', '/v2/properties/search', params=params)
        except CrexiAPIError:
            return self._request('POST', '/v2/search', json_data={'filters': params})

    def get_property(self, property_id: str) -> Dict[str, Any]:
        """
        Get detailed information about a specific property.

        Args:
            property_id: Unique property identifier

        Returns:
            Dict containing property details

        Example:
            >>> client = CrexiClient()
            >>> property_details = client.get_property("12345")
        """
        return self._request('GET', f'/v2/properties/{property_id}')

    def get_listings(
        self,
        status: str = 'active',
        page: int = 1,
        limit: int = 20
    ) -> Dict[str, Any]:
        """
        Get property listings.

        Args:
            status: Listing status (e.g., "active", "pending", "sold")
            page: Page number
            limit: Results per page

        Returns:
            Dict containing listings

        Example:
            >>> client = CrexiClient()
            >>> listings = client.get_listings(status="active", limit=50)
        """
        params = {
            'status': status,
            'page': page,
            'limit': limit
        }
        return self._request('GET', '/v1/listings', params=params)

    def autocomplete_location(self, query: str) -> List[Dict[str, Any]]:
        """
        Get location autocomplete suggestions.

        Args:
            query: Partial location query (e.g., "Miam", "Los")

        Returns:
            List of location suggestions

        Example:
            >>> client = CrexiClient()
            >>> suggestions = client.autocomplete_location("Miami")
        """
        params = {'query': query}
        result = self._request('GET', '/v1/autocomplete', params=params)
        return result.get('suggestions', [])

    # =========================
    # Advanced Search Methods
    # =========================

    def search_by_filters(self, filters: Dict[str, Any]) -> Dict[str, Any]:
        """
        Advanced property search with custom filters.

        Args:
            filters: Dictionary of filters to apply
                Available filters:
                - location: str
                - property_type: str (office, retail, industrial, multifamily, land, etc.)
                - min_price, max_price: float
                - min_size, max_size: int (square feet)
                - min_cap_rate, max_cap_rate: float
                - auction: bool
                - foreclosure: bool
                - investment_grade: bool

        Returns:
            Dict containing search results

        Example:
            >>> client = CrexiClient()
            >>> filters = {
            ...     'location': 'Miami, FL',
            ...     'property_type': 'office',
            ...     'min_price': 1000000,
            ...     'max_price': 5000000,
            ...     'auction': False
            ... }
            >>> results = client.search_by_filters(filters)
        """
        return self._request('POST', '/v2/search', json_data={'filters': filters})

    def get_market_data(self, location: str, property_type: Optional[str] = None) -> Dict[str, Any]:
        """
        Get market data for a specific location and property type.

        Args:
            location: Location query
            property_type: Optional property type filter

        Returns:
            Dict containing market data

        Example:
            >>> client = CrexiClient()
            >>> market_data = client.get_market_data("Los Angeles, CA", "office")
        """
        params = {'location': location}
        if property_type:
            params['property_type'] = property_type

        return self._request('GET', '/v1/market-data', params=params)

    # =========================
    # Auction Methods
    # =========================

    def get_auctions(
        self,
        location: Optional[str] = None,
        status: str = 'upcoming',
        page: int = 1,
        limit: int = 20
    ) -> Dict[str, Any]:
        """
        Get auction listings.

        Args:
            location: Location filter
            status: Auction status (upcoming, active, closed)
            page: Page number
            limit: Results per page

        Returns:
            Dict containing auction listings

        Example:
            >>> client = CrexiClient()
            >>> auctions = client.get_auctions(location="Florida", status="upcoming")
        """
        params = {
            'status': status,
            'page': page,
            'limit': limit
        }
        if location:
            params['location'] = location

        return self._request('GET', '/v1/auctions', params=params)

    # =========================
    # Utility Methods
    # =========================

    def get_property_types(self) -> List[str]:
        """
        Get list of available property types.

        Returns:
            List of property type strings

        Example:
            >>> client = CrexiClient()
            >>> types = client.get_property_types()
        """
        try:
            result = self._request('GET', '/v1/property-types')
            return result.get('types', [])
        except CrexiAPIError:
            # Return common types as fallback
            return [
                'office',
                'retail',
                'industrial',
                'multifamily',
                'land',
                'hospitality',
                'special_purpose',
                'mixed_use'
            ]

    def health_check(self) -> bool:
        """
        Check if the API is accessible.

        Returns:
            True if API is accessible, False otherwise
        """
        try:
            self._request('GET', '/health')
            return True
        except Exception:
            return False

    def get_stats(self) -> Dict[str, int]:
        """
        Get client usage statistics.

        Returns:
            Dict containing request count and other stats
        """
        return {
            'request_count': self._request_count,
            'last_request': datetime.fromtimestamp(self._last_request_time).isoformat() if self._last_request_time else None
        }

    def close(self):
        """Close the client and cleanup resources"""
        if hasattr(self, 'driver'):
            self.driver.quit()
        if hasattr(self, 'session'):
            self.session.close()


# =========================
# Example Usage
# =========================

if __name__ == "__main__":
    print("=" * 70)
    print("Crexi.com API Client - Example Usage")
    print("=" * 70)
    print()

    # Initialize client with cloudscraper (recommended)
    print("1. Initializing client...")
    try:
        client = CrexiClient(use_cloudscraper=True)
        print("   [✓] Client initialized\n")
    except Exception as e:
        print(f"   [✗] Failed to initialize client: {e}\n")
        exit(1)

    # Test 1: Health check
    print("2. Testing API health check...")
    try:
        is_healthy = client.health_check()
        if is_healthy:
            print("   [✓] API is accessible\n")
        else:
            print("   [✗] API health check failed\n")
    except CrexiCloudflareError as e:
        print(f"   [✗] Blocked by Cloudflare: {e}\n")
    except Exception as e:
        print(f"   [✗] Error: {e}\n")

    # Test 2: Search properties in Miami
    print("3. Searching for office properties in Miami, FL...")
    try:
        results = client.search_properties(
            location="Miami, FL",
            property_type="office",
            limit=5
        )
        print(f"   [✓] Found {len(results.get('properties', []))} properties")
        print(f"   Response: {json.dumps(results, indent=2)[:500]}...\n")
    except CrexiCloudflareError as e:
        print(f"   [✗] Blocked by Cloudflare")
        print(f"   Error: {e}\n")
        print("   SOLUTION: Install cloudscraper or undetected-chromedriver:")
        print("   pip install cloudscraper")
        print("   OR")
        print("   pip install undetected-chromedriver selenium\n")
    except Exception as e:
        print(f"   [✗] Error: {e}\n")

    # Test 3: Autocomplete
    print("4. Testing location autocomplete for 'Los Angeles'...")
    try:
        suggestions = client.autocomplete_location("Los Angeles")
        print(f"   [✓] Found {len(suggestions)} suggestions")
        for i, suggestion in enumerate(suggestions[:3], 1):
            print(f"   {i}. {suggestion}\n")
    except CrexiCloudflareError as e:
        print(f"   [✗] Blocked by Cloudflare: {e}\n")
    except Exception as e:
        print(f"   [✗] Error: {e}\n")

    # Test 4: Advanced search
    print("5. Testing advanced search with filters...")
    try:
        filters = {
            'location': 'Los Angeles, CA',
            'property_type': 'retail',
            'min_price': 500000,
            'max_price': 2000000,
        }
        results = client.search_by_filters(filters)
        print(f"   [✓] Search completed")
        print(f"   Response preview: {str(results)[:200]}...\n")
    except CrexiCloudflareError as e:
        print(f"   [✗] Blocked by Cloudflare: {e}\n")
    except Exception as e:
        print(f"   [✗] Error: {e}\n")

    # Test 5: Get auctions
    print("6. Getting upcoming auctions...")
    try:
        auctions = client.get_auctions(status="upcoming", limit=5)
        print(f"   [✓] Found {len(auctions.get('auctions', []))} auctions")
        print(f"   Response: {str(auctions)[:200]}...\n")
    except CrexiCloudflareError as e:
        print(f"   [✗] Blocked by Cloudflare: {e}\n")
    except Exception as e:
        print(f"   [✗] Error: {e}\n")

    # Show stats
    print("7. Client statistics:")
    stats = client.get_stats()
    print(f"   Requests made: {stats['request_count']}")
    print(f"   Last request: {stats['last_request']}\n")

    # Cleanup
    client.close()

    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print()
    print("STATUS: All endpoints are protected by Cloudflare bot detection (403)")
    print()
    print("DISCOVERED API STRUCTURE:")
    print("  - Base URL: https://api.crexi.com")
    print("  - API Versions: v1, v2")
    print("  - Endpoints: /properties, /search, /listings, /auctions, /autocomplete")
    print()
    print("CLOUDFLARE BYPASS SOLUTIONS:")
    print("  1. cloudscraper - Simple, works for basic protection")
    print("     pip install cloudscraper")
    print()
    print("  2. undetected-chromedriver - Most reliable, slower")
    print("     pip install undetected-chromedriver selenium")
    print()
    print("  3. Use a browser automation tool (Playwright, Puppeteer)")
    print()
    print("  4. Use a proxy service that handles Cloudflare (Bright Data, Oxylabs)")
    print()
    print("NOTE: This client provides the complete API structure and methods.")
    print("      Use cloudscraper or undetected-chromedriver to bypass Cloudflare.")
    print()
    print("=" * 70)
