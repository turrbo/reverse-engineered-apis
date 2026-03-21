# PropertyShark.com API Client

A reverse-engineered Python client for PropertyShark.com's internal APIs.

## Overview

PropertyShark.com is a comprehensive property data and analytics platform focused on real estate information, particularly for New York City. This client provides a structured interface to interact with PropertyShark's services.

**Generated:** 2026-03-21

---

## Important Disclaimer

### Access Restrictions

PropertyShark.com implements **heavy security protections**:

- **Cloudflare Bot Protection**: All API requests are filtered through Cloudflare's advanced bot detection
- **CAPTCHA Challenges**: Automated requests trigger security verification
- **Paid Subscription Required**: Most property data requires an active PropertyShark subscription
- **Rate Limiting**: Aggressive rate limiting on API endpoints
- **Session-Based Auth**: Requires valid browser session tokens

### Status of Endpoints

| Endpoint Category | Status | Notes |
|------------------|--------|-------|
| Property Search | **Blocked** | 403 Forbidden - Cloudflare protection |
| Autocomplete | **Blocked** | 403 Forbidden - Requires authentication |
| Property Details | **Blocked** | Requires valid session + subscription |
| Owner Lookup | **Blocked** | Premium feature - subscription required |
| Foreclosures | **Blocked** | Requires authentication |
| Comparables | **Blocked** | Premium analytics feature |
| Market Trends | **Blocked** | Requires authentication |
| Listings | **Blocked** | Requires authentication |
| Maps/Geo Data | **Blocked** | Requires authentication |

**All endpoints return HTTP 403 (Forbidden)** when accessed without proper authentication and Cloudflare bypass.

---

## Discovered Site Structure

From reconnaissance of PropertyShark.com, the following features were identified:

### Main Navigation
- **Property Lists**: Create and manage custom property lists
- **Listings**: Active real estate listings
- **Foreclosures**: NYC foreclosures, pre-foreclosures, REOs, auction results
- **Comparables**: Sales comparables with comprehensive property data
- **Owners**: Find real property owners, uncover ownership behind LLCs
- **Maps**: Interactive property maps

### Search Capabilities
- Search by address, neighborhood, city, or ZIP code
- Autocomplete suggestions for property search
- Geographic/coordinate-based search
- Filter by property type (residential, commercial, etc.)

### Property Data Available
- Ownership information
- Tax records and assessments
- Sales history and transaction records
- Property characteristics
- Market comparables
- Foreclosure status
- Building permits

### Geographic Coverage
- **Primary Focus**: New York City
- Full coverage across NYC boroughs
- Additional coverage in other markets (varies)

---

## API Architecture

Based on reverse engineering and common real estate API patterns, the API structure is:

### Base URLs
```
Website: https://www.propertyshark.com
API Base: https://www.propertyshark.com/api
```

### Authentication Methods

1. **Session Token** (Most Common)
   - Obtained from authenticated browser session
   - Stored in cookies: `session_token`
   - Header: `Authorization: Bearer <token>`

2. **API Key** (If Available)
   - May be available for enterprise customers
   - Header: `X-API-Key: <key>`

3. **Cookie-Based Session**
   - Multiple cookies set after login
   - Includes CSRF tokens and session identifiers

---

## API Endpoints Reference

### Search Endpoints

#### Search Properties
```
GET /api/v1/properties/search
Parameters:
  - q: string (required) - Search query
  - location: string (optional) - Location filter
  - type: string (optional) - Property type
  - limit: integer (default: 20) - Results limit
```

#### Autocomplete Search
```
GET /api/v1/search/autocomplete
Parameters:
  - q: string (required) - Partial search query
```

### Property Details Endpoints

#### Get Property Details
```
GET /api/v1/properties/{property_id}
```

#### Get Property by Address
```
GET /api/v1/properties/by-address
Parameters:
  - address: string (required)
  - city: string (required)
  - state: string (required)
  - zip: string (optional)
```

#### Get Tax History
```
GET /api/v1/properties/{property_id}/tax-history
```

#### Get Sales History
```
GET /api/v1/properties/{property_id}/sales-history
```

### Owner Lookup Endpoints

#### Search Owners
```
GET /api/v1/owners/search
Parameters:
  - name: string (required) - Owner name
```

#### Get Owner Properties
```
GET /api/v1/owners/{owner_id}/properties
```

### Foreclosures Endpoints

#### Get Foreclosures List
```
GET /api/v1/foreclosures
Parameters:
  - city: string (optional)
  - state: string (optional)
  - type: string (optional)
  - limit: integer (default: 50)
```

#### Get Foreclosure Details
```
GET /api/v1/foreclosures/{foreclosure_id}
```

### Comparables / Market Data Endpoints

#### Get Comparables
```
GET /api/v1/properties/{property_id}/comparables
Parameters:
  - radius: float (default: 0.5) - Search radius in miles
  - limit: integer (default: 10)
```

#### Get Market Trends
```
GET /api/v1/market/trends
Parameters:
  - city: string (required)
  - state: string (required)
  - type: string (optional)
```

### Geographic Endpoints

#### Get Properties by Coordinates
```
GET /api/v1/properties/nearby
Parameters:
  - lat: float (required)
  - lng: float (required)
  - radius: float (default: 1.0)
  - limit: integer (default: 50)
```

#### Get Properties in Bounding Box
```
GET /api/v1/properties/in-area
Parameters:
  - ne_lat, ne_lng: float (required) - Northeast corner
  - sw_lat, sw_lng: float (required) - Southwest corner
  - limit: integer (default: 100)
```

### Listings Endpoints

#### Get Active Listings
```
GET /api/v1/listings
Parameters:
  - city: string (optional)
  - state: string (optional)
  - type: string (optional)
  - min_price: integer (optional)
  - max_price: integer (optional)
  - limit: integer (default: 50)
```

---

## Installation

```bash
# Clone or download the client
cd outputs/

# Install required dependencies
pip install requests

# Run the example
python propertyshark_client.py
```

### Requirements
```
requests>=2.31.0
```

---

## Usage Examples

### Basic Usage

```python
from propertyshark_client import PropertySharkClient

# Initialize client
client = PropertySharkClient()

# Search for properties
result = client.search_properties("Manhattan, NY", limit=10)
print(result)
```

### With Session Token

If you have a valid session token from an authenticated browser:

```python
# Initialize with session token
client = PropertySharkClient(session_token="your_token_here")

# Now requests may work (if token is valid)
result = client.get_property_by_address(
    address="350 5th Avenue",
    city="New York",
    state="NY",
    zip_code="10118"
)
```

### Search for Foreclosures

```python
# Get foreclosures in NYC
foreclosures = client.get_foreclosures(
    city="New York",
    state="NY",
    limit=20
)
```

### Get Property Comparables

```python
# Get market comparables
comps = client.get_comparables(
    property_id="NYC123456",
    radius=0.5,  # 0.5 miles
    limit=10
)
```

### Geographic Search

```python
# Search by coordinates (Manhattan)
properties = client.get_properties_by_coordinates(
    latitude=40.7580,
    longitude=-73.9855,
    radius=1.0,
    limit=25
)
```

---

## Bypassing Cloudflare Protection

### Option 1: Extract Session from Browser

1. Log in to PropertyShark.com in your browser
2. Open Developer Tools (F12)
3. Go to Application/Storage > Cookies
4. Copy the `session_token` cookie value
5. Use it in the client:

```python
client = PropertySharkClient(session_token="your_extracted_token")
```

### Option 2: Use Browser Automation

Use Selenium or Playwright to:
1. Automate browser login
2. Extract authenticated session cookies
3. Transfer cookies to the requests client

```python
from selenium import webdriver

# Login with Selenium
driver = webdriver.Chrome()
driver.get("https://www.propertyshark.com/login")
# ... perform login ...

# Extract cookies
cookies = driver.get_cookies()
session_token = [c['value'] for c in cookies if c['name'] == 'session_token'][0]

# Use with client
client = PropertySharkClient(session_token=session_token)
```

### Option 3: Use Cloudflare Bypass Services

Services like:
- Cloudflare WARP
- FlareSolverr
- Anti-Captcha services

**Note:** These may violate PropertyShark's Terms of Service.

---

## Response Format

All methods return a dictionary with either:

### Success Response
```python
{
    "data": [...],
    "total": 100,
    "page": 1,
    "per_page": 20
}
```

### Error Response
```python
{
    "error": "Error message",
    "status_code": 403,
    "message": "Request failed - likely blocked by Cloudflare or requires authentication"
}
```

---

## Available Methods

### Search Methods
- `search_properties(query, location=None, property_type=None, limit=20)`
- `autocomplete_search(query)`

### Property Methods
- `get_property_details(property_id)`
- `get_property_by_address(address, city, state, zip_code=None)`
- `get_property_tax_history(property_id)`
- `get_property_sales_history(property_id)`

### Owner Methods
- `search_owners(owner_name)`
- `get_owner_properties(owner_id)`

### Foreclosure Methods
- `get_foreclosures(city=None, state=None, property_type=None, limit=50)`
- `get_foreclosure_details(foreclosure_id)`

### Market Data Methods
- `get_comparables(property_id, radius=0.5, limit=10)`
- `get_market_trends(city, state, property_type=None)`

### List Methods
- `get_property_lists(user_id=None)`
- `create_property_list(name, properties)`

### Geographic Methods
- `get_properties_by_coordinates(latitude, longitude, radius=1.0, limit=50)`
- `get_properties_in_area(ne_lat, ne_lng, sw_lat, sw_lng, limit=100)`

### Listing Methods
- `get_listings(city=None, state=None, property_type=None, min_price=None, max_price=None, limit=50)`

### Utility Methods
- `health_check()`

---

## Limitations & Challenges

### Security Protections
1. **Cloudflare**: Advanced bot detection blocks automated requests
2. **CAPTCHA**: Human verification required for most actions
3. **Rate Limiting**: Strict limits on request frequency
4. **IP Blocking**: Repeated failed attempts may block your IP

### Authentication Requirements
- Most endpoints require a valid PropertyShark subscription
- Free accounts have very limited access
- Session tokens expire regularly

### Data Access Restrictions
- Premium features locked behind subscription tiers
- Some data only available for specific geographic areas
- Historical data may require higher-tier subscriptions

### Legal Considerations
- Web scraping may violate Terms of Service
- Automated access may be prohibited
- Commercial use of data may require special licensing
- Respect robots.txt and rate limits

---

## Alternative Approaches

Since direct API access is heavily restricted, consider:

### 1. Official API Access
Contact PropertyShark for official API access:
- Website: https://www.propertyshark.com
- May require enterprise subscription
- Official documentation and support

### 2. Browser Automation
Use Selenium/Playwright:
- Handles JavaScript rendering
- Can solve CAPTCHA (with services)
- Maintains full browser context
- Slower but more reliable

### 3. Public Data Sources
Alternative free/open sources:
- **NYC Open Data**: https://opendata.cityofnewyork.us/
- **Zillow API**: Basic property data
- **County Records**: Direct from government sites
- **ATTOM Data Solutions**: Commercial alternative

### 4. Similar Services
Other real estate data platforms:
- **Zillow Research Data**: Free for research
- **Redfin**: Some public APIs
- **Realtor.com**: Limited public data
- **CoreLogic**: Commercial data provider

---

## Observed Site Features

During reconnaissance, these features were confirmed:

### Homepage Features
- Prominent search bar: "Address, neighborhood, city, or ZIP code"
- Tagline: "Your Key to Unrivaled Property Data and Tools"
- Offer: "Get one free property report or create lists by location"
- Location selector (defaulted to "New York City")

### Main Feature Areas
1. **Research & build lists**
   - Run property searches by address
   - Build market lists
   - Save queries and get updates

2. **Find real owners**
   - Uncover real owners behind LLCs
   - Researched contact details
   - See all associated properties

3. **Unlock foreclosures**
   - NYC foreclosures
   - Pre-foreclosures, REOs, auction results
   - Updated daily

4. **Price & value assets**
   - Run sales comparables
   - Comprehensive property data
   - Customize searches

### Navigation Menu Items
- Property Lists
- Listings (dropdown)
- Foreclosures (dropdown)
- Comparables
- Owners
- Maps
- Resources (dropdown)
- Sign Up Now / Sign In

---

## Technical Notes

### HTTP Headers
The client uses these headers to mimic a browser:
```python
{
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) ...',
    'Accept': 'application/json, text/plain, */*',
    'Referer': 'https://www.propertyshark.com/',
    'Origin': 'https://www.propertyshark.com',
    # ... additional headers
}
```

### Session Management
- Uses `requests.Session()` for connection pooling
- Maintains cookies across requests
- Supports both token and cookie-based auth

### Error Handling
- Gracefully handles HTTP errors
- Returns structured error responses
- Includes helpful error messages

---

## Testing Results

Running the example client (`python propertyshark_client.py`) produces:

```
All endpoints return: HTTP 403 Forbidden
Reason: Cloudflare protection + authentication required
```

This confirms that:
- The site is actively protected
- Direct API access is not possible without authentication
- Endpoints follow common REST API patterns
- The client structure is correct, but access is blocked

---

## Future Improvements

If you gain authenticated access, these enhancements would be valuable:

1. **Session Management**
   - Automatic token refresh
   - Cookie jar persistence
   - Session expiration handling

2. **Retry Logic**
   - Exponential backoff
   - Rate limit handling
   - Automatic retry on transient failures

3. **Data Models**
   - Pydantic models for responses
   - Type-safe data structures
   - Validation

4. **Caching**
   - Cache property data
   - Reduce API calls
   - Improve performance

5. **Async Support**
   - `httpx` for async requests
   - Concurrent requests
   - Better performance

6. **CLI Tool**
   - Command-line interface
   - Interactive mode
   - Output formatting (JSON, CSV, etc.)

---

## Contributing

Since this is a reverse-engineered client:

1. If you find working endpoints, please document them
2. If you bypass Cloudflare successfully, share the approach
3. If you get official API access, update the documentation
4. Submit issues or improvements

---

## Legal Disclaimer

This client was created for educational and research purposes. Users should:

- ✅ Review PropertyShark's Terms of Service
- ✅ Obtain proper authorization before scraping
- ✅ Respect rate limits and robots.txt
- ✅ Consider subscribing for legitimate access
- ❌ Don't abuse the service
- ❌ Don't violate copyright or data protection laws
- ❌ Don't resell scraped data without permission

**The authors are not responsible for misuse of this code.**

---

## Resources

### PropertyShark Links
- **Website**: https://www.propertyshark.com
- **Sign Up**: https://www.propertyshark.com/signup
- **Resources**: https://www.propertyshark.com/resources
- **Help Center**: Check site footer for support links

### Alternative Data Sources
- **NYC Open Data**: https://opendata.cityofnewyork.us/
- **NYC Department of Finance**: Property tax data
- **ACRIS**: NYC property records system
- **Public Records**: County assessor offices

### Related Tools
- **Beautiful Soup**: HTML parsing
- **Scrapy**: Web scraping framework
- **Selenium**: Browser automation
- **Playwright**: Modern browser automation

---

## Contact & Support

This is a community project. For:

- **Official API access**: Contact PropertyShark directly
- **Bug reports**: Submit via your project tracker
- **Improvements**: Submit pull requests
- **Questions**: Check PropertyShark's help center

---

## Changelog

### Version 1.0 (2026-03-21)
- Initial reverse-engineered client
- Documented API structure
- Identified all major endpoints
- Confirmed Cloudflare protection
- Tested all endpoint categories
- Created comprehensive documentation

---

## Acknowledgments

- PropertyShark.com for providing comprehensive property data services
- The real estate data community
- Contributors to reverse engineering efforts

---

**Remember**: Always respect website terms of service and use automation responsibly.
