# Zillow API Client (Unofficial)

Reverse-engineered Python client for Zillow's internal APIs.

## Overview

This project documents the internal API endpoints used by Zillow.com and provides a Python client to access the publicly available endpoints. Through reverse engineering, we've discovered multiple API endpoints, though most are protected by PerimeterX bot detection.

## Discovered API Endpoints

### 1. Autocomplete API ✅ Working

**Endpoint:** `https://www.zillowstatic.com/autocomplete/v3/suggestions`

**Method:** GET

**Parameters:**
- `q` (string): Search query (address, city, zip code, etc.)

**Authentication:** None required

**Response Format:** JSON

**Example Request:**
```bash
curl "https://www.zillowstatic.com/autocomplete/v3/suggestions?q=Beverly+Hills%2C+CA"
```

**Response Structure:**
```json
{
  "results": [
    {
      "display": "Beverly Hills, CA",
      "resultType": "Region",
      "metaData": {
        "regionId": 10389,
        "regionType": "city",
        "city": "Beverly Hills",
        "county": "Los Angeles County",
        "state": "CA",
        "country": "United States",
        "lat": 34.078526293682785,
        "lng": -118.40211399090684
      }
    }
  ]
}
```

**Use Cases:**
- Search for cities, zip codes, neighborhoods
- Find specific property addresses
- Get ZPIDs (Zillow Property IDs) for properties
- Geocode addresses
- Discover region IDs for area searches

### 2. Property Value History API ⚠️ Limited Access

**Endpoint:** `https://www.zillow.com/ajax/homedetail/HomeValueChartData.htm`

**Method:** GET

**Parameters:**
- `zpid` (string): Zillow Property ID
- `mt` (string): Market type (1 = standard)

**Authentication:** Subject to bot protection

**Response Format:** TSV (Tab-Separated Values)

**Example Request:**
```bash
curl "https://www.zillow.com/ajax/homedetail/HomeValueChartData.htm?zpid=20533168&mt=1"
```

**Response Structure:**
```
Date	Value	Series	Label
03/01/2016	2913287	20533168	This home
04/01/2016	3225971	20533168	This home
...
```

**Status:** This endpoint returns 403 Forbidden for most requests due to PerimeterX protection. It may work occasionally or require specific request patterns.

### 3. GraphQL API 🔒 Protected

**Endpoint:** `https://www.zillow.com/graphql/`

**Method:** POST

**Authentication:** Persisted query safelist required

**Status:** Zillow's GraphQL endpoint uses a "persisted query" security mechanism that only allows pre-approved query hashes. Arbitrary queries return:
```json
{
  "errors": [{
    "message": "The operation body was not found in the persisted query safelist",
    "extensions": {"code": "QUERY_NOT_IN_SAFELIST"}
  }]
}
```

To use this endpoint, you would need to:
1. Extract persisted query hashes from Zillow's frontend JavaScript bundles
2. Reverse engineer the query structure and variables
3. Include proper authentication tokens

**Known Query Types** (from frontend analysis):
- `ForSaleDoubleScrollFullRenderQuery` - Property search results
- `HomeDetailsQuery` - Individual property details
- `SearchQuery` - General search
- `RegionQuery` - Regional market data

### 4. Additional Protected Endpoints 🔒

All of these endpoints return 403 Forbidden due to PerimeterX bot protection:

- `/ajax/homedetail/HomeInfo.htm` - Property details
- `/ajax/homedetail/HomeValueComps.htm` - Comparable sales
- `/ajax/homedetail/NearbyHomes.htm` - Nearby properties
- `/ajax/homedetail/TaxHistory.htm` - Tax history
- `/ajax/homedetail/PriceHistory.htm` - Price history
- `/search/GetSearchPageState.htm` - Search results
- `/async-create-search-page-state` - Search state creation

## Bot Protection (PerimeterX)

Zillow uses **PerimeterX** (now HUMAN Security) for bot detection and mitigation. This system:

- Analyzes browser fingerprints
- Monitors user behavior patterns
- Requires solving CAPTCHA challenges for suspicious traffic
- Blocks automated requests with 403 responses

**PerimeterX Configuration Found:**
```javascript
window._pxAppId = 'PXHYx10rg3';
window._pxHostUrl = '/HYx10rg3/xhr';
```

### Bypassing Bot Protection

To access protected endpoints, you would need to:

1. **Use a real browser** with tools like Selenium or Playwright
2. **Solve CAPTCHA challenges** when presented
3. **Extract and reuse cookies** from a valid browser session
4. **Mimic browser behavior** including:
   - Mouse movements
   - Timing patterns
   - JavaScript execution
   - Canvas fingerprinting
5. **Use residential proxies** to avoid IP-based blocking

## Installation

```bash
pip install requests
```

No additional dependencies required for the basic client.

## Usage

### Quick Start

```python
from zillow_client import ZillowClient

# Create client
client = ZillowClient()

# Search for locations
results = client.autocomplete("Beverly Hills, CA")
for location in results:
    print(f"{location.display} - {location.result_type}")
```

### Search for Properties

```python
# Find specific properties
properties = client.search_properties("1600 Amphitheatre Parkway")
for prop in properties:
    print(f"{prop.display}")
    print(f"  ZPID: {prop.zpid}")
    print(f"  Coordinates: ({prop.latitude}, {prop.longitude})")
```

### Search for Regions

```python
# Find regions (cities, zip codes, neighborhoods)
regions = client.search_regions("California")
for region in regions:
    print(f"{region.display}")
    print(f"  Region ID: {region.region_id}")
    print(f"  Region Type: {region.region_type}")
```

### Get Property Value History (Limited)

```python
# This may not work due to bot protection
try:
    history = client.get_property_value_history("20533168")
    print(f"Latest value: ${history.values[-1]:,.0f}")
except Exception as e:
    print(f"Error: {e}")
```

## API Client Features

- **Type-safe:** Uses Python dataclasses and type hints
- **Simple:** Clean, intuitive API
- **Error handling:** Graceful handling of API errors
- **Documented:** Comprehensive docstrings
- **Tested:** Includes test examples

## Client Methods

### `autocomplete(query: str) -> List[Location]`

Search for locations, addresses, and properties.

**Parameters:**
- `query`: Search string (address, city, zip code, etc.)

**Returns:** List of `Location` objects

### `search_properties(location: str) -> List[Location]`

Search specifically for property addresses.

**Parameters:**
- `location`: Address or location query

**Returns:** List of `Location` objects with ZPIDs

### `search_regions(location: str) -> List[Location]`

Search for regions (cities, zip codes, neighborhoods).

**Parameters:**
- `location`: Location query

**Returns:** List of `Location` objects with region IDs

### `get_property_value_history(zpid: str) -> PropertyValueHistory`

Get historical property values (Zestimate history).

**Parameters:**
- `zpid`: Zillow Property ID

**Returns:** `PropertyValueHistory` object

**Note:** This method is subject to bot protection and may not work consistently.

## Data Models

### Location

```python
@dataclass
class Location:
    display: str                  # Display name
    result_type: str             # "Region" or "Address"
    region_id: Optional[int]     # Region identifier
    region_type: Optional[str]   # "city", "zipcode", etc.
    city: Optional[str]          # City name
    state: Optional[str]         # State abbreviation
    zipcode: Optional[str]       # ZIP code
    latitude: Optional[float]    # Latitude
    longitude: Optional[float]   # Longitude
    zpid: Optional[int]          # Zillow Property ID
```

### PropertyValueHistory

```python
@dataclass
class PropertyValueHistory:
    dates: List[str]    # List of dates (MM/DD/YYYY format)
    values: List[float] # Corresponding property values
    zpid: str           # Zillow Property ID
```

## Limitations

1. **Most endpoints are protected:** Only autocomplete API is reliably accessible
2. **No authentication mechanism:** No way to authenticate for protected endpoints
3. **Rate limiting:** Unknown, but excessive requests will trigger bot detection
4. **No official support:** This is a reverse-engineered client, not officially supported
5. **Subject to changes:** Zillow can change their API at any time

## Advanced: Accessing Protected Endpoints

If you need to access protected endpoints, consider:

### Option 1: Browser Automation

```python
from selenium import webdriver
from selenium.webdriver.chrome.options import Options

options = Options()
options.add_argument('--disable-blink-features=AutomationControlled')
driver = webdriver.Chrome(options=options)

# Navigate to Zillow and let user solve CAPTCHA manually
driver.get('https://www.zillow.com/beverly-hills-ca/')
input("Solve CAPTCHA and press Enter...")

# Extract cookies
cookies = driver.get_cookies()

# Use cookies with requests
import requests
session = requests.Session()
for cookie in cookies:
    session.cookies.set(cookie['name'], cookie['value'])

# Now try protected endpoints
response = session.get('https://www.zillow.com/ajax/homedetail/HomeInfo.htm?zpid=20533168')
```

### Option 2: Proxy Services

Use services like:
- ScraperAPI
- Bright Data (formerly Luminati)
- Oxylabs
- Smartproxy

These services handle bot detection bypass for you.

### Option 3: Official API (If Available)

Check if Zillow offers an official API for your use case. As of 2026, Zillow has discontinued their public API (Zillow API was shut down in 2021), but they may have partner programs.

## Discovered API Patterns

### Request Headers Pattern

```python
headers = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) ...',
    'Accept': 'application/json',
    'Accept-Language': 'en-US,en;q=0.9',
    'Accept-Encoding': 'gzip, deflate, br',
    'Origin': 'https://www.zillow.com',
    'Referer': 'https://www.zillow.com/',
    'sec-ch-ua': '"Not_A Brand";v="8", "Chromium";v="120"',
    'sec-ch-ua-mobile': '?0',
    'sec-ch-ua-platform': '"macOS"',
    'sec-fetch-dest': 'empty',
    'sec-fetch-mode': 'cors',
    'sec-fetch-site': 'same-origin',
}
```

### GraphQL Query Pattern (Blocked)

```python
payload = {
    "operationName": "SearchQuery",
    "variables": {
        "searchQueryState": {
            "pagination": {"currentPage": 1},
            "usersSearchTerm": "Beverly Hills, CA",
            "filterState": {...},
            "isListVisible": True,
            "mapZoom": 12
        }
    },
    "query": "query SearchQuery(...) { ... }",
    "extensions": {
        "persistedQuery": {
            "version": 1,
            "sha256Hash": "..."  # Required hash from frontend
        }
    }
}
```

## Testing

Run the included test suite:

```bash
python zillow_client.py
```

This will test all available endpoints and display results.

## Legal Notice

This client is for educational and research purposes only. When using this client:

1. **Respect Zillow's Terms of Service**
2. **Don't overload their servers** with excessive requests
3. **Use rate limiting** in your applications
4. **Don't use for commercial purposes** without permission
5. **Consider using official APIs** when available

Unauthorized scraping or API access may violate Zillow's Terms of Service and could result in:
- IP blocking
- Legal action
- Account termination (if applicable)

## Contributing

This is a research project documenting Zillow's internal APIs. If you discover additional endpoints or patterns, please document them following the format above.

## Changelog

**2026-03-21** - Initial release
- Discovered autocomplete API endpoint
- Documented GraphQL endpoint (persisted queries)
- Identified PerimeterX bot protection
- Created Python client for accessible endpoints

## Future Work

- [ ] Reverse engineer persisted query hashes
- [ ] Document GraphQL schema
- [ ] Add browser automation examples
- [ ] Implement rate limiting
- [ ] Add caching layer
- [ ] Create async client version
- [ ] Add retry logic with exponential backoff

## Resources

- **Zillow Website:** https://www.zillow.com
- **PerimeterX/HUMAN Security:** https://www.humansecurity.com/
- **Requests Library:** https://requests.readthedocs.io/

## License

This project is provided for educational purposes only. Use at your own risk.
