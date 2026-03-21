"""
CarGurus API Client
===================

A reverse-engineered Python client for the CarGurus internal API.

IMPORTANT NOTES:
- CarGurus uses Cloudflare protection and bot detection
- Direct API access may require solving CAPTCHAs or using browser automation
- This client provides the structure and methods, but may require additional
  authentication handling (cookies, tokens) obtained through browser sessions
- Consider using Selenium/Playwright for production use to handle dynamic protection

Author: Reverse Engineered API Client
Date: 2026-03-21
"""

import requests
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from enum import Enum
import json
from urllib.parse import urlencode, quote


class SortBy(Enum):
    """Sort options for search results"""
    BEST_MATCH = "best_match"
    PRICE_LOW_HIGH = "price_asc"
    PRICE_HIGH_LOW = "price_desc"
    MILEAGE_LOW_HIGH = "mileage_asc"
    MILEAGE_HIGH_LOW = "mileage_desc"
    DISTANCE = "distance"
    YEAR_NEW_OLD = "year_desc"
    YEAR_OLD_NEW = "year_asc"


class BodyStyle(Enum):
    """Vehicle body styles"""
    SEDAN = "sedan"
    SUV = "suv"
    TRUCK = "truck"
    COUPE = "coupe"
    CONVERTIBLE = "convertible"
    WAGON = "wagon"
    HATCHBACK = "hatchback"
    MINIVAN = "minivan"


@dataclass
class SearchFilters:
    """Search filters for vehicle listings"""
    zip_code: str
    distance: int = 50  # miles
    make: Optional[str] = None
    model: Optional[str] = None
    min_year: Optional[int] = None
    max_year: Optional[int] = None
    min_price: Optional[int] = None
    max_price: Optional[int] = None
    min_mileage: Optional[int] = None
    max_mileage: Optional[int] = None
    body_style: Optional[BodyStyle] = None
    sort_by: SortBy = SortBy.BEST_MATCH
    page: int = 1
    per_page: int = 15

    def to_params(self) -> Dict[str, Any]:
        """Convert filters to API parameters"""
        params = {
            "zip": self.zip_code,
            "distance": self.distance,
            "page": self.page,
            "perPage": self.per_page,
        }

        if self.make and self.model:
            # CarGurus uses hyphenated format: "toyota-camry"
            params["makeModelName"] = f"{self.make.lower()}-{self.model.lower()}"
        elif self.make:
            params["make"] = self.make

        if self.min_year:
            params["minYear"] = self.min_year
        if self.max_year:
            params["maxYear"] = self.max_year
        if self.min_price:
            params["minPrice"] = self.min_price
        if self.max_price:
            params["maxPrice"] = self.max_price
        if self.min_mileage:
            params["minMileage"] = self.min_mileage
        if self.max_mileage:
            params["maxMileage"] = self.max_mileage
        if self.body_style:
            params["bodyStyle"] = self.body_style.value
        if self.sort_by:
            params["sortBy"] = self.sort_by.value

        return params


class CarGurusClient:
    """
    CarGurus API Client

    This client provides methods to interact with CarGurus' internal APIs.
    Due to bot protection, you may need to provide session cookies or use
    browser automation to obtain valid tokens.
    """

    BASE_URL = "https://www.cargurus.com"

    # Known API endpoints (reverse engineered)
    ENDPOINTS = {
        "listings": "/Cars/inventorylisting/viewDetailsFilterViewInventoryListing.action",
        "listing_detail": "/Cars/inventorylisting/viewListingDetail.action",
        "dealer_info": "/Cars/api-external/v1/dealer",
        "price_trends": "/Cars/api/pricetrends",
        "reviews": "/api/reviews",
        "saved_search": "/Cars/api-overview/v1/savedSearch",
        "instant_market_value": "/Cars/instantMarketValue",
    }

    def __init__(
        self,
        session_cookies: Optional[Dict[str, str]] = None,
        user_agent: Optional[str] = None
    ):
        """
        Initialize CarGurus client

        Args:
            session_cookies: Optional cookies from authenticated session
            user_agent: Custom user agent string (defaults to mobile)
        """
        self.session = requests.Session()

        # Set default headers
        self.session.headers.update({
            "User-Agent": user_agent or (
                "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) "
                "AppleWebKit/605.1.15 (KHTML, like Gecko) "
                "Version/16.0 Mobile/15E148 Safari/604.1"
            ),
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": self.BASE_URL,
            "X-Requested-With": "XMLHttpRequest",
        })

        # Add session cookies if provided
        if session_cookies:
            self.session.cookies.update(session_cookies)

    def _make_request(
        self,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        method: str = "GET"
    ) -> Dict[str, Any]:
        """
        Make API request with error handling

        Args:
            endpoint: API endpoint path
            params: Query parameters
            method: HTTP method

        Returns:
            JSON response data

        Raises:
            requests.exceptions.RequestException: On request failure
        """
        url = f"{self.BASE_URL}{endpoint}"

        try:
            if method.upper() == "GET":
                response = self.session.get(url, params=params, timeout=30)
            else:
                response = self.session.post(url, json=params, timeout=30)

            response.raise_for_status()

            # Try to parse JSON response
            try:
                return response.json()
            except json.JSONDecodeError:
                # If not JSON, return text content
                return {"content": response.text, "status_code": response.status_code}

        except requests.exceptions.RequestException as e:
            print(f"Request failed: {e}")
            if hasattr(e, 'response') and e.response is not None:
                print(f"Response status: {e.response.status_code}")
                print(f"Response text: {e.response.text[:500]}")
            raise

    def search_listings(self, filters: SearchFilters) -> Dict[str, Any]:
        """
        Search for vehicle listings

        Args:
            filters: SearchFilters object with search criteria

        Returns:
            Dictionary containing search results with listings array

        Example:
            ```python
            filters = SearchFilters(
                zip_code="90210",
                make="Toyota",
                model="Camry",
                max_price=30000,
                max_mileage=50000
            )
            results = client.search_listings(filters)
            ```
        """
        params = filters.to_params()
        return self._make_request(self.ENDPOINTS["listings"], params)

    def get_listing_detail(self, listing_id: str) -> Dict[str, Any]:
        """
        Get detailed information for a specific listing

        Args:
            listing_id: The unique listing ID

        Returns:
            Dictionary containing detailed listing information
        """
        params = {"listingId": listing_id}
        return self._make_request(self.ENDPOINTS["listing_detail"], params)

    def get_dealer_info(self, dealer_id: str) -> Dict[str, Any]:
        """
        Get dealer information

        Args:
            dealer_id: The dealer's unique ID

        Returns:
            Dictionary containing dealer information
        """
        endpoint = f"{self.ENDPOINTS['dealer_info']}/{dealer_id}"
        return self._make_request(endpoint)

    def get_price_trends(
        self,
        make: str,
        model: str,
        year: int,
        zip_code: str
    ) -> Dict[str, Any]:
        """
        Get price trend data for a vehicle

        Args:
            make: Vehicle make (e.g., "Toyota")
            model: Vehicle model (e.g., "Camry")
            year: Vehicle year
            zip_code: ZIP code for location-based pricing

        Returns:
            Dictionary containing price trend data
        """
        params = {
            "make": make,
            "model": model,
            "year": year,
            "zip": zip_code
        }
        return self._make_request(self.ENDPOINTS["price_trends"], params)

    def get_instant_market_value(
        self,
        make: str,
        model: str,
        year: int,
        mileage: int,
        zip_code: str,
        trim: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Get instant market value (IMV) for a vehicle

        Args:
            make: Vehicle make
            model: Vehicle model
            year: Vehicle year
            mileage: Current mileage
            zip_code: ZIP code
            trim: Optional trim level

        Returns:
            Dictionary containing IMV data
        """
        params = {
            "make": make,
            "model": model,
            "year": year,
            "mileage": mileage,
            "zip": zip_code
        }
        if trim:
            params["trim"] = trim

        return self._make_request(self.ENDPOINTS["instant_market_value"], params)

    def get_reviews(
        self,
        make: str,
        model: str,
        year: Optional[int] = None,
        page: int = 1
    ) -> Dict[str, Any]:
        """
        Get user reviews for a vehicle

        Args:
            make: Vehicle make
            model: Vehicle model
            year: Optional specific year
            page: Page number for pagination

        Returns:
            Dictionary containing reviews data
        """
        params = {
            "make": make,
            "model": model,
            "page": page
        }
        if year:
            params["year"] = year

        return self._make_request(self.ENDPOINTS["reviews"], params)

    def create_saved_search(self, filters: SearchFilters, name: str) -> Dict[str, Any]:
        """
        Create a saved search (requires authentication)

        Args:
            filters: SearchFilters object
            name: Name for the saved search

        Returns:
            Dictionary containing saved search confirmation
        """
        params = filters.to_params()
        params["searchName"] = name
        return self._make_request(
            self.ENDPOINTS["saved_search"],
            params,
            method="POST"
        )

    def get_makes(self) -> List[str]:
        """
        Get list of available vehicle makes

        Returns:
            List of make names
        """
        # This would typically be available in their metadata API
        # For now, return common makes
        return [
            "Toyota", "Honda", "Ford", "Chevrolet", "Nissan", "BMW",
            "Mercedes-Benz", "Audi", "Volkswagen", "Hyundai", "Kia",
            "Mazda", "Subaru", "Lexus", "Jeep", "Ram", "GMC", "Dodge",
            "Acura", "Infiniti", "Volvo", "Porsche", "Tesla", "Cadillac"
        ]

    def build_search_url(self, filters: SearchFilters) -> str:
        """
        Build a CarGurus search URL for browser access

        Args:
            filters: SearchFilters object

        Returns:
            Full URL string for the search
        """
        params = filters.to_params()
        query_string = urlencode(params)
        return f"{self.BASE_URL}{self.ENDPOINTS['listings']}?{query_string}"


class CarGurusAPIError(Exception):
    """Custom exception for CarGurus API errors"""
    pass


# Utility functions

def format_price(price: int) -> str:
    """Format price as currency string"""
    return f"${price:,}"


def format_mileage(mileage: int) -> str:
    """Format mileage with comma separator"""
    return f"{mileage:,} miles"


def calculate_monthly_payment(
    price: int,
    down_payment: int = 0,
    interest_rate: float = 5.0,
    term_months: int = 60
) -> float:
    """
    Calculate estimated monthly payment

    Args:
        price: Vehicle price
        down_payment: Down payment amount
        interest_rate: Annual interest rate (percentage)
        term_months: Loan term in months

    Returns:
        Monthly payment amount
    """
    loan_amount = price - down_payment
    monthly_rate = (interest_rate / 100) / 12

    if monthly_rate == 0:
        return loan_amount / term_months

    monthly_payment = loan_amount * (
        monthly_rate * (1 + monthly_rate) ** term_months
    ) / ((1 + monthly_rate) ** term_months - 1)

    return round(monthly_payment, 2)


# Example usage
if __name__ == "__main__":
    print("CarGurus API Client - Example Usage")
    print("=" * 50)

    # Initialize client
    client = CarGurusClient()

    # Example 1: Basic search
    print("\n1. Searching for Toyota Camry near 90210...")
    print("-" * 50)

    filters = SearchFilters(
        zip_code="90210",
        make="Toyota",
        model="Camry",
        max_price=35000,
        max_mileage=50000,
        min_year=2020
    )

    try:
        # Build search URL (works even with bot protection)
        search_url = client.build_search_url(filters)
        print(f"Search URL: {search_url}")
        print("\nNote: Direct API access is blocked by Cloudflare protection.")
        print("To use this client in production, you need to:")
        print("1. Use Selenium/Playwright to get valid session cookies")
        print("2. Pass cookies to CarGurusClient(session_cookies={...})")
        print("3. Or use the generated URLs in a browser automation tool")

        # Attempt API call (will likely fail due to protection)
        print("\n\nAttempting direct API call...")
        results = client.search_listings(filters)

        if "content" in results:
            print("Received HTML response (likely CAPTCHA page)")
        else:
            print(f"Found {len(results.get('listings', []))} listings")

    except Exception as e:
        print(f"API call failed (expected due to bot protection): {e}")

    # Example 2: Price trend lookup
    print("\n\n2. Price trends for 2022 Honda Accord...")
    print("-" * 50)
    try:
        trends = client.get_price_trends(
            make="Honda",
            model="Accord",
            year=2022,
            zip_code="90210"
        )
        print("Price trends:", json.dumps(trends, indent=2))
    except Exception as e:
        print(f"Failed: {e}")

    # Example 3: Calculate payment
    print("\n\n3. Calculate monthly payment...")
    print("-" * 50)
    payment = calculate_monthly_payment(
        price=30000,
        down_payment=5000,
        interest_rate=4.5,
        term_months=60
    )
    print(f"Vehicle Price: {format_price(30000)}")
    print(f"Down Payment: {format_price(5000)}")
    print(f"Interest Rate: 4.5%")
    print(f"Term: 60 months")
    print(f"Monthly Payment: {format_price(int(payment))}")

    # Example 4: Available makes
    print("\n\n4. Available vehicle makes...")
    print("-" * 50)
    makes = client.get_makes()
    print(f"Total makes: {len(makes)}")
    print(f"Sample: {', '.join(makes[:10])}")

    print("\n\n" + "=" * 50)
    print("IMPORTANT NOTES:")
    print("=" * 50)
    print("""
This client provides the API structure for CarGurus, but direct access
is blocked by Cloudflare bot protection. To use in production:

1. Browser Automation Approach (Recommended):
   - Use Selenium or Playwright
   - Navigate to CarGurus and solve CAPTCHA
   - Extract session cookies
   - Pass cookies to: CarGurusClient(session_cookies={...})

2. URL Generation Approach:
   - Use client.build_search_url() to generate valid URLs
   - Use browser automation to visit these URLs
   - Parse results from rendered HTML

3. Mobile App API:
   - Reverse engineer the mobile app
   - Extract API tokens and endpoints
   - Use different base URLs that may have less protection

Example with Selenium:
```python
from selenium import webdriver
driver = webdriver.Chrome()
driver.get("https://www.cargurus.com")
# Solve CAPTCHA manually or wait
cookies = {c['name']: c['value'] for c in driver.get_cookies()}
client = CarGurusClient(session_cookies=cookies)
results = client.search_listings(filters)
```
""")
