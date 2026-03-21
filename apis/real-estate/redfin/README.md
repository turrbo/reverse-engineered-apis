# Redfin API Client

A production-ready Python client for accessing Redfin's undocumented Stingray API. This client allows you to search for property listings, get market data, and export property information without requiring authentication.

**Reverse engineered on:** 2026-03-21

---

## Features

- Search properties by region with advanced filters
- Get region and market information
- Export property data to CSV format
- Search for recently sold properties
- Type hints and comprehensive docstrings
- Production-ready with proper error handling
- Rate limiting to avoid WAF blocks
- Connection reuse with requests.Session

---

## Installation

```bash
pip install requests
```

No additional dependencies required!

---

## Quick Start

```python
from redfin_client import RedfinClient

# Initialize the client
client = RedfinClient()

# Search for properties in Boston
listings = client.search_properties(
    region_id=1826,
    region_type=RedfinClient.REGION_TYPE_CITY,
    num_homes=10
)

# Print results
for listing in listings:
    print(f"${listing.price:,} - {listing.beds}bd/{listing.baths}ba")
    print(f"{listing.address}, {listing.city}, {listing.state}")
    print()
```

---

## Discovered Endpoints

### Working Endpoints ✅

| Endpoint | Method | Description | Status |
|----------|--------|-------------|--------|
| `/stingray/api/region` | GET | Get region metadata and defaults | ✅ Working |
| `/stingray/api/gis` | GET | Search properties with filters | ✅ Working |
| `/stingray/api/gis-csv` | GET | Export property data to CSV | ✅ Working |

### Blocked Endpoints ⛔

| Endpoint | Method | Description | Status |
|----------|--------|-------------|--------|
| `/stingray/api/home/details/belowTheFold` | GET | Get detailed property information | ⛔ Blocked by WAF |
| `/stingray/api/home/details/aboveTheFold` | GET | Get property overview | ⛔ Blocked by WAF |
| `/stingray/do/location-autocomplete` | GET | Location search suggestions | ⛔ Blocked by WAF |

---

## API Documentation

### Region Types

Use these constants when specifying region types:

- `REGION_TYPE_NEIGHBORHOOD = 1` - Specific neighborhood
- `REGION_TYPE_ZIP = 2` - ZIP/postal code
- `REGION_TYPE_COUNTY = 4` - County level
- `REGION_TYPE_CITY = 6` - City level
- `REGION_TYPE_METRO = 8` - Metropolitan area

### Property Types

- `PROPERTY_TYPE_SINGLE_FAMILY = 1`
- `PROPERTY_TYPE_CONDO = 2`
- `PROPERTY_TYPE_TOWNHOUSE = 3`
- `PROPERTY_TYPE_MULTI_FAMILY = 4`
- `PROPERTY_TYPE_LAND = 6`
- `PROPERTY_TYPE_OTHER = 7`

---

## Usage Examples

### Example 1: Get Region Information

```python
client = RedfinClient()

# Get info for ZIP code 17420
region_info = client.get_region_info(
    region_id=17420,
    region_type=RedfinClient.REGION_TYPE_ZIP
)

print(region_info['payload']['rootDefaults']['region_name'])
print(region_info['payload']['rootDefaults']['market'])
```

### Example 2: Search with Price Filters

```python
client = RedfinClient()

# Search for homes in Boston between $300k-$500k
listings = client.search_properties(
    region_id=1826,
    region_type=RedfinClient.REGION_TYPE_CITY,
    num_homes=50,
    min_price=300000,
    max_price=500000,
    min_beds=2
)

for listing in listings:
    if listing.price:
        print(f"${listing.price:,} - {listing.address}")
```

### Example 3: Export to CSV

```python
client = RedfinClient()

# Export properties to CSV
csv_data = client.export_properties_csv(
    region_id=1826,
    region_type=RedfinClient.REGION_TYPE_CITY,
    num_homes=100
)

# Save to file
with open('boston_properties.csv', 'w') as f:
    f.write(csv_data)
```

### Example 4: Search Recent Sales

```python
client = RedfinClient()

# Get homes sold in the last 30 days
recent_sales = client.search_recent_sales(
    region_id=17420,
    region_type=RedfinClient.REGION_TYPE_ZIP,
    days=30,
    num_homes=50
)

for sale in recent_sales:
    print(f"${sale.price:,} - {sale.address} ({sale.status})")
```

### Example 5: Filter by Property Type

```python
client = RedfinClient()

# Search only for single-family homes and townhouses
listings = client.search_properties(
    region_id=1826,
    region_type=RedfinClient.REGION_TYPE_CITY,
    num_homes=20,
    property_types=[
        RedfinClient.PROPERTY_TYPE_SINGLE_FAMILY,
        RedfinClient.PROPERTY_TYPE_TOWNHOUSE
    ]
)
```

---

## Authentication

**No authentication required!** The Redfin Stingray API endpoints that are accessible do not require API keys, OAuth tokens, or any other form of authentication.

However, some endpoints are protected by AWS CloudFront WAF (Web Application Firewall) and will block programmatic access. The client includes proper browser-like headers to minimize detection, but certain endpoints (like detailed property information) are still blocked.

---

## Rate Limiting

The client includes built-in rate limiting to avoid triggering WAF blocks:

```python
# Set custom rate limit (default: 0.5 seconds between requests)
client = RedfinClient(rate_limit_delay=1.0)
```

**Recommendations:**
- Use at least 0.5 seconds between requests
- For heavy scraping, consider 1-2 seconds
- Monitor for 403 errors and increase delay if blocked

---

## Response Format

The Redfin API returns JSONP-style responses with a `{}&&` prefix:

```
{}&&{"version":633,"resultCode":0,"payload":{...}}
```

The client automatically strips this prefix and parses the JSON.

---

## Common Region IDs

Here are some region IDs for major cities (use `REGION_TYPE_CITY`):

- **Boston, MA**: 1826
- **New York, NY**: 30749
- **San Francisco, CA**: 17151
- **Los Angeles, CA**: 11203
- **Chicago, IL**: 29470
- **Seattle, WA**: 16163

To find region IDs for other locations:
1. Go to Redfin.com and search for the location
2. Look at the URL: `/city/12345/` - the number is the region ID
3. Or inspect network traffic in browser DevTools

---

## Error Handling

The client raises `RedfinAPIError` for all API-related errors:

```python
from redfin_client import RedfinClient, RedfinAPIError

client = RedfinClient()

try:
    listings = client.search_properties(region_id=1826)
except RedfinAPIError as e:
    print(f"API Error: {e}")
```

Common errors:
- **403 Forbidden**: Blocked by CloudFront WAF (try increasing rate limit)
- **Page not found**: Invalid endpoint or parameters
- **Request failed**: Network error or timeout

---

## Advanced Configuration

### Using a Custom Session

```python
import requests

session = requests.Session()
session.proxies = {
    'http': 'http://proxy.example.com:8080',
    'https': 'https://proxy.example.com:8080'
}

client = RedfinClient(session=session)
```

### Custom Headers

```python
client = RedfinClient()
client.session.headers['X-Custom-Header'] = 'value'
```

---

## Limitations

### WAF Protection
Redfin uses AWS CloudFront WAF to protect against scraping. The following endpoints are blocked:
- Property detail pages (`/home/details/*`)
- Location autocomplete
- Most endpoints requiring `propertyId` parameter

### Data Accuracy
- Some MLS listings may be excluded per local MLS rules
- Data may be slightly delayed from real-time
- Not all properties have complete information

### No Search by Address
The working endpoints require a `region_id`. To search by address:
1. Manually look up the region ID on Redfin.com
2. Or use the blocked autocomplete endpoint (requires browser-based scraping)

---

## Troubleshooting

### Getting 403 Errors

If you're getting blocked:

1. **Increase rate limiting:**
   ```python
   client = RedfinClient(rate_limit_delay=2.0)
   ```

2. **Use residential proxies** (commercial proxies may be blocked)

3. **Rotate User-Agent strings**

4. **Consider using Selenium/Playwright** for endpoints that require browser-based access

### Finding Region IDs

**Method 1: From Redfin URL**
```
https://www.redfin.com/city/1826/MA/Boston
                           ^^^^
                        region_id
```

**Method 2: Browser DevTools**
1. Open Redfin.com in browser
2. Search for a location
3. Open Network tab in DevTools
4. Look for `gis` or `region` API calls
5. Check the `region_id` parameter

---

## Testing

Run the built-in test suite:

```bash
python redfin_client.py
```

This will test:
- ✅ Region information retrieval
- ✅ Property search with filters
- ✅ Recent sales search
- ✅ CSV export
- ⛔ Property details (expected to fail)

---

## Use Cases

- **Real Estate Analysis**: Analyze market trends and pricing
- **Property Research**: Find properties matching specific criteria
- **Data Collection**: Export property data for analysis
- **Market Monitoring**: Track new listings and sales
- **Investment Analysis**: Research neighborhoods and price ranges

---

## Legal & Ethical Considerations

- ⚠️ This API is **undocumented and unofficial**
- ⚠️ Redfin may change or block access at any time
- ⚠️ Respect Redfin's terms of service and robots.txt
- ⚠️ Use rate limiting to avoid overloading their servers
- ⚠️ For commercial use, contact Redfin for official API access

**This tool is for educational and research purposes only.**

---

## Contributing

This is a reverse-engineered client. If you discover new working endpoints or improvements:

1. Test the endpoint with curl
2. Document the request/response format
3. Add the method to the client
4. Update this README

---

## Changelog

### 2026-03-21 - Initial Release

- ✅ Region information endpoint
- ✅ Property search with filters
- ✅ CSV export
- ✅ Recent sales search
- ✅ Type hints and dataclasses
- ✅ Rate limiting
- ✅ Production-ready error handling

---

## Support

For issues, questions, or improvements:
- Review the test suite output for working examples
- Check browser DevTools Network tab for API patterns
- Test endpoints with curl before implementing in Python

---

## License

This is an educational reverse-engineering project. Use at your own risk.

**Not affiliated with or endorsed by Redfin Corporation.**
