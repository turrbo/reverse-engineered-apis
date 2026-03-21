# AutoTempest Unofficial API Client

Python client for searching car listings across 10+ sources via AutoTempest's internal API.

## What It Does

AutoTempest aggregates listings from eBay Motors, Cars.com, Carvana, CarMax, Hemmings, Facebook Marketplace, Craigslist, and more. This client hits their internal endpoints directly -- no scraping, no Selenium, no browser needed.

## Endpoints Discovered

| Endpoint | Auth | Purpose |
|---|---|---|
| `/api/get-makes` | None | List all car makes |
| `/api/get-models/{make}` | None | List models for a make |
| `/api/truecar/makes-models` | None | Full make/model catalog |
| `/queue-results` | HMAC token | Car listings from all sources |
| `/api/facebookMarketplace` | HMAC token | Facebook Marketplace results |
| `/api/searchtempest/direct` | HMAC token | Craigslist results |

## Install

```bash
pip install requests
```

## Usage

```python
from autotempest_client import AutoTempestClient

client = AutoTempestClient()

# List all makes
makes = client.get_makes()

# Search for Toyota near Beverly Hills
results = client.search(
    make="toyota",
    zip_code="90210",
    radius=50,
    max_price=30000,
    min_year=2020,
    sort="price_asc",
)

for car in results.get("results", []):
    print(f"{car['title']} - {car['price']} - {car['mileage']} mi")
    print(f"  VIN: {car['vin']} | {car['location']}")

# Search ALL sources at once
all_results = client.search_all_sources(
    make="bmw",
    zip_code="10001",
    radius=50,
)
print(f"Found {all_results['total']} listings across all sources")
```

## Search Parameters

| Parameter | Values |
|---|---|
| `sort` | `best_match`, `price_asc`, `price_desc`, `miles_asc`, `miles_desc`, `year_asc`, `year_desc`, `date_asc`, `date_desc`, `dist_asc` |
| `transmission` | `any`, `man`, `auto` |
| `fuel` | `any`, `gas`, `diesel`, `electric`, `hybrid` |
| `drive` | `any`, `fwd`, `rwd`, `awd`, `4wd` |
| `body_style` | `any`, `sedan`, `coupe`, `suv`, `truck`, `convertible`, `wagon`, `hatchback`, `minivan`, `van` |
| `sale_by` | `any`, `dealer`, `private` |
| `sale_type` | `any`, `auction`, `classified` |
| `sites` | `te` (AutoTempest), `hem` (Hemmings), `cs` (Cars.com), `cv` (Carvana), `cm` (CarMax), `eb` (eBay), `ot` (Other), `fbm` (Facebook Marketplace), `st` (Craigslist) |

## Response Schema

Each listing includes:

```
title, price, mileage, year, make, model, trim, vin,
location, distance, dealerName, sellerType,
priceHistory, img, url, vehicleTitle, ...
```

## How It Was Built

Reverse-engineered using browser network interception:

1. Navigated to autotempest.com, injected fetch/XHR interceptors
2. Triggered searches to capture API calls via `performance.getEntriesByType()`
3. Downloaded webpack JS bundles, found token generation: `SHA-256(params + secret)`
4. Extracted the hash constant from the minified source
5. Verified token generation matches, built and tested the client

## Disclaimer

This is an unofficial client for educational/research purposes. AutoTempest's internal API may change without notice. Use responsibly and respect their terms of service.
