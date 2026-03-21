# LoopNet.com Unofficial API Client

## Overview

This is an **unofficial, educational** Python client for reverse-engineering LoopNet.com's API. LoopNet is the leading commercial real estate marketplace with over 300,000+ active listings.

**IMPORTANT DISCLAIMER**: This client is for educational and research purposes only. LoopNet employs aggressive bot protection that will block most automated access. Use at your own risk and respect LoopNet's Terms of Service.

## Current Status: BLOCKED BY BOT PROTECTION

### Challenge Encountered

During reverse engineering attempts, we encountered:

- **Akamai Bot Protection**: LoopNet uses Akamai's aggressive bot detection
- **403 Forbidden Errors**: All automated requests are blocked
- **Access Denied Pages**: Even with realistic headers and user agents
- **Console Execution Detection**: Running JavaScript in the console triggers blocks
- **Navigation Blocking**: Navigating between pages programmatically triggers protection

### Evidence

```
Access Denied
You don't have permission to access "http://www.loopnet.com/" on this server.
Reference #18.98dcda17.1774089703.259a3899
https://errors.edgesuite.net/18.98dcda17.1774089703.259a3899
```

## Architecture Analysis

Based on reconnaissance, LoopNet appears to use:

### Frontend
- Modern React-based SPA (Single Page Application)
- Heavy client-side rendering
- Dynamic property search with real-time filters

### Backend Structure (Inferred)
- RESTful API endpoints (likely at `/api/*`)
- Possible GraphQL endpoint for complex queries
- Server-side rendering for SEO
- CDN distribution via Akamai

### Potential API Endpoints

While we couldn't confirm these due to bot protection, commercial real estate sites typically use:

```
GET  /api/search                    - Search properties
GET  /api/property/{id}             - Get property details
GET  /api/autocomplete              - Location autocomplete
GET  /api/featured                  - Featured listings
GET  /api/search/nearby             - Geospatial search
GET  /api/market/stats              - Market statistics
POST /api/favorites                 - Save favorites (authenticated)
POST /graphql                       - GraphQL queries
```

## Authentication

LoopNet likely uses:
- Session cookies
- JWT tokens (in localStorage or cookies)
- CSRF tokens for POST requests
- API keys for partner integrations

## The Python Client

### Features

The provided `loopnet_client.py` includes:

- Session management with connection pooling
- Realistic browser headers
- Type hints and comprehensive docstrings
- Multiple endpoint fallback strategies
- Proxy support
- Cookie/session injection
- Property search with filters
- Location autocomplete
- Property details retrieval
- Geospatial coordinate search
- Market statistics
- GraphQL query support

### Installation

```bash
pip install requests
```

### Basic Usage

```python
from loopnet_client import LoopNetClient, SearchFilters, PropertyType, ListingType

# Initialize client
client = LoopNetClient()

# Search for properties
filters = SearchFilters(
    location="New York, NY",
    property_type=PropertyType.OFFICE,
    listing_type=ListingType.FOR_SALE,
    min_price=1000000,
    max_price=10000000
)

try:
    results = client.search_properties(filters)
    print(f"Found {len(results['results'])} properties")
except Exception as e:
    print(f"Search failed: {e}")  # Will fail due to bot protection
```

### Test Results

When running the test suite, all endpoints return **404 Not Found** or are blocked:

| Endpoint | Status | Notes |
|----------|--------|-------|
| `/api/search` | 404 | Not the actual endpoint |
| `/api/v1/search` | 404 | Version not used |
| `/api/v2/search` | 404 | Version not used |
| `/api/autocomplete` | 404 | Not the actual endpoint |
| `/api/property/{id}` | 404 | Not the actual endpoint |
| `/api/featured` | 404 | Not the actual endpoint |
| `/api/market/stats` | 404 | Not the actual endpoint |
| `/graphql` | Not tested | Likely exists but protected |

## Bypassing Bot Protection

To successfully interact with LoopNet's API, you would need:

### 1. Browser Automation

Use Selenium or Playwright with stealth plugins:

```python
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)
    context = browser.new_context(
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64)...",
        viewport={'width': 1920, 'height': 1080}
    )

    # Add stealth scripts to avoid detection
    page = context.new_page()
    page.goto("https://www.loopnet.com")

    # Extract cookies after successful page load
    cookies = context.cookies()
```

### 2. Session Cookie Extraction

After manually loading the site in a real browser:

```python
# Extract cookies from browser (use browser extension or DevTools)
session_cookies = {
    'session_id': 'your-session-id',
    'auth_token': 'your-auth-token',
    # ... other cookies
}

client = LoopNetClient(session_cookies=session_cookies)
```

### 3. Residential Proxies

Use rotating residential proxies to avoid IP bans:

```python
proxy = "http://username:password@proxy-provider.com:port"
client = LoopNetClient(proxy=proxy)
```

### 4. CAPTCHA Solving

Integrate with CAPTCHA solving services:
- 2Captcha
- Anti-Captcha
- CapSolver

### 5. Network Traffic Analysis

To find the actual endpoints, you need to:

1. Open LoopNet in a real browser
2. Open DevTools (F12) → Network tab
3. Filter by XHR/Fetch requests
4. Perform searches and interactions
5. Inspect the API calls
6. Extract:
   - Endpoint URLs
   - Request headers
   - Request payloads
   - Response formats
   - Authentication tokens

Example of what you'd see:

```
GET /api/property/search?location=new-york-ny&type=office HTTP/1.1
Host: www.loopnet.com
Authorization: Bearer eyJhbGciOiJIUzI1NiIs...
X-CSRF-Token: abc123...
Cookie: session=xyz789...
```

## Legal and Ethical Considerations

### Terms of Service

LoopNet's Terms of Service likely prohibit:
- Automated data collection (scraping)
- Using bots or automated tools
- Accessing the site through unauthorized means
- Commercial use of scraped data

### Recommended Alternatives

Instead of scraping, consider:

1. **Official LoopNet API**: Contact LoopNet/CoStar for partnership/API access
2. **Data Partnerships**: License data directly from CoStar Group
3. **Public Data Sources**: Use government property records and MLS data
4. **Third-Party APIs**: Use licensed commercial real estate data providers

## Production-Ready Approach

If you have legitimate need for LoopNet data:

### Option 1: Official Partnership
Contact CoStar Group (LoopNet's owner) for:
- API access
- Data licensing
- Integration partnerships

### Option 2: Headless Browser Solution

```python
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium_stealth import stealth
import time

# Configure stealth browser
chrome_options = Options()
chrome_options.add_argument("--disable-blink-features=AutomationControlled")
chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
chrome_options.add_experimental_option('useAutomationExtension', False)

driver = webdriver.Chrome(options=chrome_options)

# Apply stealth techniques
stealth(driver,
    languages=["en-US", "en"],
    vendor="Google Inc.",
    platform="Win32",
    webgl_vendor="Intel Inc.",
    renderer="Intel Iris OpenGL Engine",
    fix_hairline=True,
)

driver.get("https://www.loopnet.com")
time.sleep(5)  # Wait for page load

# Now extract data from DOM
properties = driver.find_elements_by_class_name("property-card")
for prop in properties:
    print(prop.text)
```

### Option 3: Scraping Framework with Respect

If you must scrape:

```python
import scrapy
from scrapy.downloadermiddlewares.retry import RetryMiddleware
from scrapy_splash import SplashRequest

class LoopNetSpider(scrapy.Spider):
    name = "loopnet"

    custom_settings = {
        'DOWNLOAD_DELAY': 3,  # Be respectful
        'CONCURRENT_REQUESTS': 1,
        'ROBOTSTXT_OBEY': True,  # Respect robots.txt
        'USER_AGENT': 'Mozilla/5.0...'
    }

    def start_requests(self):
        yield SplashRequest(
            url='https://www.loopnet.com/search/',
            callback=self.parse,
            args={'wait': 2}
        )

    def parse(self, response):
        # Extract data from rendered page
        pass
```

## Monitoring and Rate Limiting

Always implement:

```python
import time
from functools import wraps

def rate_limit(calls_per_minute=10):
    min_interval = 60.0 / calls_per_minute
    last_called = [0.0]

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            elapsed = time.time() - last_called[0]
            left_to_wait = min_interval - elapsed
            if left_to_wait > 0:
                time.sleep(left_to_wait)
            ret = func(*args, **kwargs)
            last_called[0] = time.time()
            return ret
        return wrapper
    return decorator

@rate_limit(calls_per_minute=6)  # Max 6 requests/minute
def search_properties(query):
    # Your search logic
    pass
```

## Data Structure Examples

Based on typical commercial real estate APIs, expected response formats:

### Property Search Response

```json
{
  "results": [
    {
      "id": "12345678",
      "type": "office",
      "address": {
        "street": "123 Main St",
        "city": "New York",
        "state": "NY",
        "zip": "10001",
        "lat": 40.7589,
        "lon": -73.9851
      },
      "price": 5000000,
      "size_sqft": 10000,
      "listing_type": "for-sale",
      "year_built": 1995,
      "images": ["url1", "url2"],
      "broker": {
        "name": "John Doe",
        "company": "ABC Realty",
        "phone": "555-1234"
      }
    }
  ],
  "total_count": 1234,
  "page": 1,
  "per_page": 25
}
```

### Property Details Response

```json
{
  "id": "12345678",
  "title": "Prime Manhattan Office Space",
  "description": "Luxury office space in Midtown...",
  "type": "office",
  "subtype": "class-a",
  "address": { ... },
  "price": 5000000,
  "size_sqft": 10000,
  "price_per_sqft": 500,
  "features": [
    "Elevator",
    "Parking",
    "24/7 Access"
  ],
  "images": [...],
  "virtual_tour_url": "https://...",
  "documents": [...],
  "nearby_amenities": [...],
  "market_statistics": {
    "avg_price_per_sqft": 450,
    "days_on_market": 45,
    "comparable_properties": [...]
  }
}
```

## Known Limitations

1. **Bot Protection**: Akamai blocks all automated requests
2. **Unknown Endpoints**: Actual API paths not discoverable without browser inspection
3. **Authentication**: Session/token requirements unknown
4. **Rate Limits**: Unknown, likely aggressive
5. **Data Structure**: Response formats not confirmed
6. **GraphQL Schema**: If using GraphQL, schema is undocumented

## Contributing

Since this is an educational project blocked by bot protection:

1. If you find working endpoints, please document them
2. If you successfully bypass protection, share techniques
3. Report any legal concerns
4. Suggest alternative data sources

## Resources

- [LoopNet Official Site](https://www.loopnet.com)
- [CoStar Group](https://www.costargroup.com) - Parent company
- [Akamai Bot Manager](https://www.akamai.com/products/bot-manager) - Protection system used
- [Selenium Stealth](https://github.com/diprajpatra/selenium-stealth) - Bypass automation detection
- [Playwright](https://playwright.dev/) - Modern browser automation
- [Scrapy](https://scrapy.org/) - Web scraping framework

## License

MIT License - Educational use only. Not affiliated with LoopNet or CoStar Group.

## Disclaimer

This tool is provided for educational purposes only. The authors are not responsible for any misuse or violations of LoopNet's Terms of Service. Always respect website terms and consider legal alternatives for data access.

---

**Created**: March 21, 2026
**Status**: Research/Educational
**Success Rate**: 0% (blocked by bot protection)
**Recommended Approach**: Use official API or browser automation with stealth techniques
