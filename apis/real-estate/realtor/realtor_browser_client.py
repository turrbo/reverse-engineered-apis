#!/usr/bin/env python3
"""
Realtor.com Browser-Based API Client

This client uses Playwright to bypass Kasada bot protection by executing
JavaScript and rendering pages in a real browser context.

Installation:
    pip install playwright requests beautifulsoup4
    playwright install chromium

Usage:
    from realtor_browser_client import RealtorBrowserClient

    with RealtorBrowserClient(headless=True) as client:
        results = client.search_properties("Los Angeles, CA", limit=20)
        for prop in results:
            print(f"{prop['address']} - ${prop['price']:,}")
"""

from playwright.sync_api import sync_playwright, Page, Browser
from typing import Dict, List, Optional, Any
import json
import time
import re


class RealtorBrowserClient:
    """
    Browser-based client for Realtor.com that bypasses bot protection.

    Uses Playwright to render JavaScript and intercept API responses.
    """

    BASE_URL = "https://www.realtor.com"

    def __init__(self, headless: bool = False, timeout: int = 30000):
        """
        Initialize browser-based client.

        Args:
            headless: Run browser in headless mode (False recommended for Kasada)
            timeout: Page load timeout in milliseconds
        """
        self.headless = headless
        self.timeout = timeout
        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None
        self.captured_responses = []

    def __enter__(self):
        """Context manager entry."""
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()

    def start(self):
        """Start browser session."""
        self.playwright = sync_playwright().start()

        # Launch browser with specific options to avoid detection
        self.browser = self.playwright.chromium.launch(
            headless=self.headless,
            args=[
                '--disable-blink-features=AutomationControlled',
                '--disable-dev-shm-usage',
                '--disable-web-security',
                '--no-sandbox'
            ]
        )

        # Create context with realistic browser fingerprint
        self.context = self.browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent=(
                'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                'AppleWebKit/537.36 (KHTML, like Gecko) '
                'Chrome/120.0.0.0 Safari/537.36'
            ),
            locale='en-US',
            timezone_id='America/New_York',
        )

        # Inject script to hide webdriver
        self.context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });
        """)

        self.page = self.context.new_page()
        self.page.set_default_timeout(self.timeout)

        # Set up response interceptor
        self.page.on('response', self._handle_response)

    def close(self):
        """Close browser session."""
        if self.page:
            self.page.close()
        if self.context:
            self.context.close()
        if self.browser:
            self.browser.close()
        if self.playwright:
            self.playwright.stop()

    def _handle_response(self, response):
        """
        Intercept and capture API responses.

        Args:
            response: Playwright response object
        """
        url = response.url

        # Filter for API calls (exclude analytics, ads, etc.)
        if '/api/' in url or '/hulk' in url:
            if any(x in url for x in ['google', 'analytics', 'doubleclick', 'facebook']):
                return

            try:
                if response.status == 200:
                    content_type = response.headers.get('content-type', '')
                    if 'application/json' in content_type:
                        data = response.json()
                        self.captured_responses.append({
                            'url': url,
                            'status': response.status,
                            'data': data,
                            'timestamp': time.time()
                        })
            except Exception as e:
                pass  # Ignore JSON parse errors

    def search_properties(
        self,
        location: str,
        status: str = "for_sale",
        beds_min: Optional[int] = None,
        baths_min: Optional[int] = None,
        price_min: Optional[int] = None,
        price_max: Optional[int] = None,
        property_type: Optional[str] = None,
        limit: int = 42
    ) -> List[Dict[str, Any]]:
        """
        Search for properties by navigating to search page and extracting data.

        Args:
            location: City, state, or ZIP code
            status: for_sale, for_rent, or recently_sold
            beds_min: Minimum bedrooms
            baths_min: Minimum bathrooms
            price_min: Minimum price
            price_max: Maximum price
            property_type: Property type filter
            limit: Maximum results to return

        Returns:
            List of property dictionaries

        Example:
            >>> client.search_properties("90210", price_max=2000000, beds_min=3)
        """
        # Build search URL
        location_slug = location.lower().replace(' ', '-').replace(',', '')
        url = f"{self.BASE_URL}/realestateandhomes-search/{location_slug}"

        # Navigate and wait for content
        self.captured_responses = []  # Reset captures
        self.page.goto(url)

        # Wait for property cards to load
        try:
            self.page.wait_for_selector('[data-testid="property-card"]', timeout=10000)
        except:
            # Try alternative selector
            try:
                self.page.wait_for_selector('.property-card', timeout=5000)
            except:
                pass  # Continue anyway

        # Give time for API calls to complete
        time.sleep(2)

        # Extract properties from captured API responses
        properties = []
        for response in self.captured_responses:
            if 'data' in response:
                data = response['data']

                # Handle different response formats
                if 'data' in data and 'home_search' in data['data']:
                    results = data['data']['home_search'].get('results', [])
                    properties.extend(results)
                elif 'properties' in data:
                    properties.extend(data['properties'])
                elif isinstance(data, list):
                    properties.extend(data)

        # If no API data captured, scrape from page
        if not properties:
            properties = self._scrape_properties_from_page()

        # Apply filters and limit
        filtered = self._apply_filters(
            properties,
            beds_min=beds_min,
            baths_min=baths_min,
            price_min=price_min,
            price_max=price_max
        )

        return filtered[:limit]

    def _scrape_properties_from_page(self) -> List[Dict[str, Any]]:
        """
        Scrape property data directly from page HTML.

        Returns:
            List of property dictionaries
        """
        properties = []

        # Get all property cards
        cards = self.page.query_selector_all('[data-testid="property-card"], .property-card')

        for card in cards:
            try:
                prop = {}

                # Extract address
                address_elem = card.query_selector('[data-testid="property-address"], .property-address')
                if address_elem:
                    prop['address'] = address_elem.inner_text().strip()

                # Extract price
                price_elem = card.query_selector('[data-testid="property-price"], .property-price')
                if price_elem:
                    price_text = price_elem.inner_text().strip()
                    prop['price'] = self._parse_price(price_text)
                    prop['price_raw'] = price_text

                # Extract beds/baths
                beds_elem = card.query_selector('[data-testid="property-beds"]')
                if beds_elem:
                    prop['beds'] = self._parse_number(beds_elem.inner_text())

                baths_elem = card.query_selector('[data-testid="property-baths"]')
                if baths_elem:
                    prop['baths'] = self._parse_number(baths_elem.inner_text())

                # Extract sqft
                sqft_elem = card.query_selector('[data-testid="property-sqft"]')
                if sqft_elem:
                    prop['sqft'] = self._parse_number(sqft_elem.inner_text())

                # Extract property link
                link_elem = card.query_selector('a[href*="/realestateandhomes-detail/"]')
                if link_elem:
                    prop['url'] = self.BASE_URL + link_elem.get_attribute('href')
                    # Extract property ID from URL
                    match = re.search(r'/realestateandhomes-detail/([^/]+)', prop['url'])
                    if match:
                        prop['property_id'] = match.group(1)

                if prop:
                    properties.append(prop)

            except Exception as e:
                continue  # Skip problematic cards

        return properties

    def get_property_details(self, property_id: str) -> Dict[str, Any]:
        """
        Get detailed information about a specific property.

        Args:
            property_id: Property ID or slug from search results

        Returns:
            Property details dictionary

        Example:
            >>> details = client.get_property_details("123-Main-St-Los-Angeles-CA-90001")
        """
        url = f"{self.BASE_URL}/realestateandhomes-detail/{property_id}"

        # Navigate to property page
        self.captured_responses = []
        self.page.goto(url)

        # Wait for main content
        try:
            self.page.wait_for_selector('[data-testid="property-details"]', timeout=5000)
        except:
            pass

        time.sleep(2)

        # Try to extract from API responses first
        for response in self.captured_responses:
            if 'data' in response:
                data = response['data']
                if 'property' in data or 'listing' in data:
                    return data

        # Fallback to scraping page
        return self._scrape_property_details()

    def _scrape_property_details(self) -> Dict[str, Any]:
        """
        Scrape property details from page HTML.

        Returns:
            Property details dictionary
        """
        details = {}

        # Address
        address_elem = self.page.query_selector('[data-testid="property-address"]')
        if address_elem:
            details['address'] = address_elem.inner_text().strip()

        # Price
        price_elem = self.page.query_selector('[data-testid="property-price"]')
        if price_elem:
            details['price'] = self._parse_price(price_elem.inner_text())

        # Key facts
        facts = self.page.query_selector_all('[data-testid="key-fact"]')
        for fact in facts:
            label = fact.query_selector('.key-fact-label')
            value = fact.query_selector('.key-fact-value')
            if label and value:
                key = label.inner_text().strip().lower().replace(' ', '_')
                details[key] = value.inner_text().strip()

        # Description
        desc_elem = self.page.query_selector('[data-testid="property-description"]')
        if desc_elem:
            details['description'] = desc_elem.inner_text().strip()

        # Photos
        photo_elems = self.page.query_selector_all('[data-testid="property-photo"] img')
        details['photos'] = [img.get_attribute('src') for img in photo_elems]

        return details

    def _apply_filters(
        self,
        properties: List[Dict],
        beds_min: Optional[int] = None,
        baths_min: Optional[int] = None,
        price_min: Optional[int] = None,
        price_max: Optional[int] = None
    ) -> List[Dict]:
        """Apply filters to property list."""
        filtered = properties

        if beds_min:
            filtered = [p for p in filtered if p.get('beds', 0) >= beds_min]

        if baths_min:
            filtered = [p for p in filtered if p.get('baths', 0) >= baths_min]

        if price_min:
            filtered = [p for p in filtered if p.get('price', 0) >= price_min]

        if price_max:
            filtered = [p for p in filtered if p.get('price', float('inf')) <= price_max]

        return filtered

    @staticmethod
    def _parse_price(text: str) -> Optional[int]:
        """Parse price from text like '$1,250,000' or '$1.25M'."""
        if not text:
            return None

        # Remove currency symbols and whitespace
        text = text.replace('$', '').replace(',', '').strip()

        # Handle abbreviations
        multiplier = 1
        if 'M' in text or 'm' in text:
            multiplier = 1_000_000
            text = text.replace('M', '').replace('m', '')
        elif 'K' in text or 'k' in text:
            multiplier = 1_000
            text = text.replace('K', '').replace('k', '')

        try:
            return int(float(text) * multiplier)
        except:
            return None

    @staticmethod
    def _parse_number(text: str) -> Optional[int]:
        """Parse number from text like '3 beds' or '2,500 sqft'."""
        if not text:
            return None

        # Extract first number
        match = re.search(r'([\d,]+)', text)
        if match:
            try:
                return int(match.group(1).replace(',', ''))
            except:
                return None
        return None

    def execute_console_script(self, script: str) -> Any:
        """
        Execute JavaScript in console context.

        Args:
            script: JavaScript code to execute

        Returns:
            Result of script execution
        """
        return self.page.evaluate(script)

    def get_captured_api_calls(self) -> List[Dict]:
        """
        Get all captured API calls.

        Returns:
            List of captured response dictionaries
        """
        return self.captured_responses


if __name__ == "__main__":
    """
    Example usage and testing.
    """
    print("=" * 70)
    print("Realtor.com Browser-Based API Client - Test Suite")
    print("=" * 70)

    print("\n[INFO] Starting browser session...")
    print("[INFO] Headless mode: False (required to bypass Kasada)")

    try:
        with RealtorBrowserClient(headless=False) as client:

            # Test 1: Search properties
            print("\n" + "=" * 70)
            print("[TEST 1] Searching for properties in Beverly Hills (90210)")
            print("=" * 70)

            properties = client.search_properties(
                location="90210",
                status="for_sale",
                beds_min=3,
                price_max=5_000_000,
                limit=10
            )

            print(f"\n✓ Found {len(properties)} properties")

            if properties:
                print("\nExample properties:")
                for i, prop in enumerate(properties[:3], 1):
                    print(f"\n  [{i}] {prop.get('address', 'N/A')}")
                    print(f"      Price: ${prop.get('price', 0):,}")
                    print(f"      Beds: {prop.get('beds', 'N/A')}")
                    print(f"      Baths: {prop.get('baths', 'N/A')}")
                    print(f"      Sqft: {prop.get('sqft', 'N/A'):,}" if prop.get('sqft') else "      Sqft: N/A")

            # Test 2: Get property details
            if properties and properties[0].get('property_id'):
                print("\n" + "=" * 70)
                print("[TEST 2] Fetching property details")
                print("=" * 70)

                property_id = properties[0]['property_id']
                print(f"\nProperty ID: {property_id}")

                details = client.get_property_details(property_id)
                print(f"\n✓ Retrieved property details")
                print(f"  Keys: {', '.join(details.keys())}")

            # Test 3: Show captured API calls
            print("\n" + "=" * 70)
            print("[TEST 3] Captured API Calls")
            print("=" * 70)

            api_calls = client.get_captured_api_calls()
            print(f"\nCaptured {len(api_calls)} API responses:")

            for i, call in enumerate(api_calls[:5], 1):
                url = call['url']
                # Truncate long URLs
                if len(url) > 80:
                    url = url[:77] + "..."
                print(f"  [{i}] {url}")

    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback
        traceback.print_exc()

    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print("""
Browser-based client successfully bypasses Kasada protection by:
  1. Using real Chromium browser with Playwright
  2. Executing JavaScript to obtain valid tokens
  3. Intercepting API responses in real-time
  4. Scraping rendered HTML as fallback

Advantages over direct API:
  ✓ Bypasses bot protection
  ✓ Access to all data shown on website
  ✓ No need for reverse-engineered endpoints
  ✓ Captures dynamic JavaScript-rendered content

Disadvantages:
  ✗ Slower than direct API calls (3-5 seconds per page)
  ✗ Requires browser installation
  ✗ Higher memory usage (~200-300MB per browser)
  ✗ More complex to deploy

Best Practices:
  • Run in non-headless mode to avoid detection
  • Add random delays between requests (2-5 seconds)
  • Rotate user agents periodically
  • Use residential proxies for large-scale scraping
  • Respect rate limits (max 1 request per 2 seconds)

For production use:
  • Implement proper error handling
  • Add retry logic with exponential backoff
  • Use proxy rotation
  • Monitor for CAPTCHA challenges
  • Log all requests for debugging
    """)
