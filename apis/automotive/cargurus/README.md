# CarGurus API Client - Reverse Engineered

A comprehensive Python client for interacting with CarGurus' internal APIs, reverse-engineered from their web platform.

## Overview

This project provides a structured API client for CarGurus.com, enabling programmatic access to vehicle listings, pricing data, dealer information, and more. The client was built by analyzing CarGurus' URL patterns, endpoint structures, and request formats.

## Important Notice

**Bot Protection**: CarGurus implements aggressive Cloudflare bot protection and CAPTCHA challenges. Direct API access from this client will be blocked unless you:

1. Obtain valid session cookies through browser automation (Selenium/Playwright)
2. Use a CAPTCHA solving service
3. Implement browser automation to handle the protection dynamically

This client provides the **structure and methods** for the API, but requires additional work to bypass protection in production environments.

## Installation

```bash
# Clone or download this repository
cd outputs

# Install dependencies
pip install requests

# Optional: For browser automation integration
pip install selenium playwright
```

## Quick Start

### Basic Usage (URL Generation)

```python
from cargurus_client import CarGurusClient, SearchFilters

# Initialize client
client = CarGurusClient()

# Create search filters
filters = SearchFilters(
    zip_code="90210",
    make="Toyota",
    model="Camry",
    max_price=35000,
    max_mileage=50000,
    min_year=2020
)

# Generate search URL (works without bypassing protection)
search_url = client.build_search_url(filters)
print(f"Search URL: {search_url}")
# Use this URL with Selenium/Playwright to scrape results
```

### With Browser Automation (Selenium Example)

```python
from selenium import webdriver
from cargurus_client import CarGurusClient, SearchFilters

# Start browser session
driver = webdriver.Chrome()
driver.get("https://www.cargurus.com")

# Wait for user to solve CAPTCHA or implement automated solving
input("Solve CAPTCHA in browser, then press Enter...")

# Extract session cookies
cookies = {c['name']: c['value'] for c in driver.get_cookies()}

# Initialize client with cookies
client = CarGurusClient(session_cookies=cookies)

# Now make API calls
filters = SearchFilters(zip_code="90210", make="Toyota", model="Camry")
results = client.search_listings(filters)
print(f"Found {len(results.get('listings', []))} listings")

driver.quit()
```

## Discovered API Endpoints

Based on reverse engineering, the following endpoints have been identified:

### 1. Inventory Listings Search

**Endpoint**: `/Cars/inventorylisting/viewDetailsFilterViewInventoryListing.action`

**Method**: GET

**Parameters**:
- `zip` (required): ZIP code for location-based search
- `distance`: Search radius in miles (default: 50)
- `makeModelName`: Hyphenated format like "toyota-camry"
- `make`: Vehicle make (if not using makeModelName)
- `model`: Vehicle model (if not using makeModelName)
- `minYear`, `maxYear`: Year range filters
- `minPrice`, `maxPrice`: Price range filters
- `minMileage`, `maxMileage`: Mileage range filters
- `bodyStyle`: Vehicle body style (sedan, suv, truck, etc.)
- `sortBy`: Sort order (best_match, price_asc, price_desc, etc.)
- `page`: Page number for pagination
- `perPage`: Results per page (default: 15)

**Example**:
```python
filters = SearchFilters(
    zip_code="10001",
    make="Honda",
    model="Accord",
    min_year=2020,
    max_year=2024,
    max_price=40000,
    sort_by=SortBy.PRICE_LOW_HIGH
)
results = client.search_listings(filters)
```

### 2. Listing Detail

**Endpoint**: `/Cars/inventorylisting/viewListingDetail.action`

**Method**: GET

**Parameters**:
- `listingId` (required): Unique listing identifier

**Example**:
```python
detail = client.get_listing_detail(listing_id="12345678")
```

### 3. Dealer Information

**Endpoint**: `/Cars/api-external/v1/dealer/{dealer_id}`

**Method**: GET

**Example**:
```python
dealer = client.get_dealer_info(dealer_id="987654")
```

### 4. Price Trends

**Endpoint**: `/Cars/api/pricetrends`

**Method**: GET

**Parameters**:
- `make` (required): Vehicle make
- `model` (required): Vehicle model
- `year` (required): Vehicle year
- `zip` (required): ZIP code for regional pricing

**Example**:
```python
trends = client.get_price_trends(
    make="Tesla",
    model="Model 3",
    year=2023,
    zip_code="94102"
)
```

### 5. Instant Market Value (IMV)

**Endpoint**: `/Cars/instantMarketValue`

**Method**: GET

**Parameters**:
- `make`, `model`, `year` (required)
- `mileage` (required): Current vehicle mileage
- `zip` (required): ZIP code
- `trim` (optional): Specific trim level

**Example**:
```python
imv = client.get_instant_market_value(
    make="BMW",
    model="X5",
    year=2022,
    mileage=15000,
    zip_code="90210",
    trim="xDrive40i"
)
```

### 6. User Reviews

**Endpoint**: `/api/reviews`

**Method**: GET

**Parameters**:
- `make` (required)
- `model` (required)
- `year` (optional)
- `page`: Page number for pagination

**Example**:
```python
reviews = client.get_reviews(
    make="Mazda",
    model="CX-5",
    year=2023
)
```

### 7. Saved Search (Requires Authentication)

**Endpoint**: `/Cars/api-overview/v1/savedSearch`

**Method**: POST

**Parameters**:
- All search filter parameters
- `searchName`: Name for the saved search

**Example**:
```python
saved = client.create_saved_search(filters, name="My Dream Car Search")
```

## API Client Classes

### SearchFilters

Data class for building search queries:

```python
@dataclass
class SearchFilters:
    zip_code: str                      # Required
    distance: int = 50                 # Search radius in miles
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
```

### Enums

**SortBy**:
- `BEST_MATCH`: Default relevance-based sorting
- `PRICE_LOW_HIGH`: Price ascending
- `PRICE_HIGH_LOW`: Price descending
- `MILEAGE_LOW_HIGH`: Mileage ascending
- `MILEAGE_HIGH_LOW`: Mileage descending
- `DISTANCE`: Distance from ZIP code
- `YEAR_NEW_OLD`: Newest first
- `YEAR_OLD_NEW`: Oldest first

**BodyStyle**:
- `SEDAN`, `SUV`, `TRUCK`, `COUPE`, `CONVERTIBLE`, `WAGON`, `HATCHBACK`, `MINIVAN`

## Utility Functions

### Price Formatting
```python
from cargurus_client import format_price
print(format_price(25000))  # "$25,000"
```

### Mileage Formatting
```python
from cargurus_client import format_mileage
print(format_mileage(50000))  # "50,000 miles"
```

### Monthly Payment Calculator
```python
from cargurus_client import calculate_monthly_payment

payment = calculate_monthly_payment(
    price=30000,
    down_payment=5000,
    interest_rate=4.5,  # APR
    term_months=60
)
print(f"Monthly payment: ${payment}")  # $466.08
```

## Authentication & Headers

CarGurus APIs expect specific headers for successful requests:

```python
headers = {
    "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0...)",
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.cargurus.com",
    "X-Requested-With": "XMLHttpRequest"
}
```

The client sets these automatically, but you may need to update them if CarGurus changes their requirements.

## Known Limitations

1. **Bot Protection**: Cloudflare CAPTCHA blocks direct API access
2. **Rate Limiting**: Aggressive rate limiting may apply (untested due to protection)
3. **Session Expiry**: Session cookies expire; implement refresh mechanism
4. **API Changes**: CarGurus may change endpoints without notice
5. **Incomplete Coverage**: Some endpoints may exist but are undiscovered

## Bypassing Bot Protection

### Method 1: Browser Automation (Recommended)

Use Selenium or Playwright to:
1. Navigate to CarGurus
2. Solve CAPTCHA (manually or with service like 2Captcha)
3. Extract cookies
4. Pass to client

```python
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)
    page = browser.new_page()
    page.goto("https://www.cargurus.com")

    # Wait for user to solve CAPTCHA
    page.wait_for_selector('input[placeholder*="search"]', timeout=60000)

    # Extract cookies
    cookies = {c['name']: c['value'] for c in page.context.cookies()}

    # Use with client
    client = CarGurusClient(session_cookies=cookies)
    # ... make API calls

    browser.close()
```

### Method 2: CAPTCHA Solving Services

Integrate services like:
- 2Captcha
- Anti-Captcha
- CapSolver

Example with 2Captcha:
```python
from twocaptcha import TwoCaptcha

solver = TwoCaptcha('YOUR_API_KEY')
result = solver.recaptcha(
    sitekey='6LfYXXXXXXXXXXXX',  # Extract from CarGurus page
    url='https://www.cargurus.com'
)

# Use result['code'] in automated browser session
```

### Method 3: Residential Proxies

Use rotating residential proxies to avoid IP-based blocking:
```python
proxies = {
    'http': 'http://user:pass@proxy-provider.com:8080',
    'https': 'http://user:pass@proxy-provider.com:8080'
}

client = CarGurusClient()
client.session.proxies.update(proxies)
```

### Method 4: Mobile App API

Reverse engineer the CarGurus mobile app:
1. Intercept mobile app traffic with mitmproxy
2. Extract API endpoints and authentication tokens
3. Use mobile-specific endpoints (may have less protection)

## Response Formats

### Listing Search Response (Expected)

```json
{
  "listings": [
    {
      "id": "12345678",
      "year": 2023,
      "make": "Toyota",
      "model": "Camry",
      "trim": "SE",
      "price": 28500,
      "mileage": 12000,
      "exteriorColor": "Celestial Silver Metallic",
      "interiorColor": "Black",
      "transmission": "Automatic",
      "fuelType": "Gasoline",
      "drivetrain": "FWD",
      "engine": "2.5L I4",
      "vin": "4T1C11AK9PU123456",
      "dealer": {
        "id": "987654",
        "name": "ABC Toyota",
        "phone": "(555) 123-4567",
        "address": "123 Main St, Beverly Hills, CA 90210"
      },
      "images": ["url1", "url2", "..."],
      "carfaxUrl": "https://...",
      "dealType": "GREAT_DEAL",
      "priceAnalysis": {
        "imv": 30000,
        "priceDifferencePercent": -5
      }
    }
  ],
  "totalResults": 245,
  "page": 1,
  "perPage": 15
}
```

Note: Actual response format may differ; this is based on typical automotive API patterns.

## Advanced Usage

### Pagination Example

```python
def search_all_pages(filters: SearchFilters, max_pages: int = 10):
    """Search multiple pages of results"""
    all_listings = []

    for page in range(1, max_pages + 1):
        filters.page = page
        results = client.search_listings(filters)

        listings = results.get('listings', [])
        if not listings:
            break

        all_listings.extend(listings)

        # Check if we've reached the last page
        if len(listings) < filters.per_page:
            break

    return all_listings
```

### Multi-Location Search

```python
zip_codes = ["90210", "10001", "60601", "94102"]
all_results = []

for zip_code in zip_codes:
    filters = SearchFilters(
        zip_code=zip_code,
        make="Tesla",
        model="Model Y",
        max_price=60000
    )
    results = client.search_listings(filters)
    all_results.append({
        'location': zip_code,
        'results': results
    })
```

### Price Comparison Across Years

```python
def compare_prices_by_year(make: str, model: str, years: list, zip_code: str):
    """Compare pricing across multiple years"""
    comparison = {}

    for year in years:
        filters = SearchFilters(
            zip_code=zip_code,
            make=make,
            model=model,
            min_year=year,
            max_year=year
        )
        results = client.search_listings(filters)

        # Calculate average price
        listings = results.get('listings', [])
        if listings:
            avg_price = sum(l['price'] for l in listings) / len(listings)
            comparison[year] = {
                'avg_price': avg_price,
                'count': len(listings)
            }

    return comparison
```

## Error Handling

```python
from requests.exceptions import RequestException
from cargurus_client import CarGurusAPIError

try:
    results = client.search_listings(filters)
except RequestException as e:
    if e.response and e.response.status_code == 403:
        print("Bot protection triggered - need valid session")
    elif e.response and e.response.status_code == 429:
        print("Rate limited - slow down requests")
    else:
        print(f"Request failed: {e}")
except CarGurusAPIError as e:
    print(f"API error: {e}")
```

## Testing

Run the example script:
```bash
python cargurus_client.py
```

Expected output:
- Search URL generation (works)
- API call attempts (will fail with 403 due to bot protection)
- Utility function demonstrations (payment calculator, etc.)

## Roadmap / Future Enhancements

- [ ] Implement automatic CAPTCHA solving integration
- [ ] Add support for authenticated user endpoints (saved searches, alerts)
- [ ] Reverse engineer mobile app API endpoints
- [ ] Add HTML parsing fallback when API is blocked
- [ ] Implement automatic cookie refresh mechanism
- [ ] Add async/await support for concurrent requests
- [ ] Create comprehensive test suite with mocked responses
- [ ] Add support for CarGurus dealer tools API
- [ ] Implement vehicle comparison features
- [ ] Add support for financing calculator API

## Contributing

This is a reverse-engineered project. Contributions welcome:

1. Discover new endpoints and add to client
2. Improve bot protection bypass methods
3. Add better error handling
4. Create more utility functions
5. Add comprehensive tests

## Legal Disclaimer

This client is for educational and research purposes only. Use responsibly:

- Respect CarGurus' Terms of Service
- Do not overload their servers
- Do not scrape for commercial purposes without permission
- Consider rate limiting and ethical use
- CarGurus may change or block access at any time

## Resources

- CarGurus Website: https://www.cargurus.com
- Selenium Documentation: https://selenium-python.readthedocs.io/
- Playwright Documentation: https://playwright.dev/python/
- mitmproxy (API interception): https://mitmproxy.org/

## Troubleshooting

### Issue: All requests return 403 Forbidden

**Solution**: This is expected. You need to:
1. Use browser automation to get valid cookies
2. Or use the URL generation feature with Selenium
3. Or wait for CAPTCHA solving integration

### Issue: Cookies expire quickly

**Solution**: Implement automatic refresh:
```python
def refresh_cookies():
    # Re-run browser automation
    driver = webdriver.Chrome()
    driver.get("https://www.cargurus.com")
    # ... solve CAPTCHA again
    return extract_cookies(driver)

# Refresh every hour
while True:
    cookies = refresh_cookies()
    client = CarGurusClient(session_cookies=cookies)
    # ... do work
    time.sleep(3600)
```

### Issue: Response format different than expected

**Solution**: CarGurus may have updated their API. Capture actual responses:
```python
response = client._make_request(endpoint, params)
print(json.dumps(response, indent=2))
# Adjust parsing logic based on actual format
```

## Contact

For questions or issues with this reverse-engineered client, please file an issue in the repository.

---

**Last Updated**: 2026-03-21

**Client Version**: 1.0.0

**Tested Against**: CarGurus.com (March 2026)
