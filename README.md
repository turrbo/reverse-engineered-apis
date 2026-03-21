# Reverse-Engineered APIs

Collection of unofficial API clients built by reverse-engineering websites' hidden/internal endpoints.

## Automotive

| Site | Directory | Status | Description |
|---|---|---|---|
| [AutoTempest](apis/automotive/autotempest/) | `apis/automotive/autotempest/` | Full access | Car listings across 10+ sources (eBay, Cars.com, Carvana, CarMax, etc.) |
| [CarGurus](apis/automotive/cargurus/) | `apis/automotive/cargurus/` | Cloudflare-protected | Vehicle search, pricing, dealer info, instant market value |

## Real Estate

| Site | Directory | Status | Description |
|---|---|---|---|
| [Zillow](apis/real-estate/zillow/) | `apis/real-estate/zillow/` | Partial access | Property autocomplete, geocoding, ZPID lookup, region search |
| [Redfin](apis/real-estate/redfin/) | `apis/real-estate/redfin/` | Partial access | Stingray API -- property search, CSV export, region data (no auth required) |
| [Realtor.com](apis/real-estate/realtor/) | `apis/real-estate/realtor/` | Kasada-protected | 10 endpoints mapped, GraphQL API, requires browser automation |
| [LoopNet](apis/real-estate/loopnet/) | `apis/real-estate/loopnet/` | Akamai-protected | Commercial real estate, endpoints mapped but blocked by Akamai Bot Manager |
| [Crexi](apis/real-estate/crexi/) | `apis/real-estate/crexi/` | Cloudflare-protected | 16 commercial real estate endpoints, property search, auctions, market data |
| [PropertyShark](apis/real-estate/propertyshark/) | `apis/real-estate/propertyshark/` | Cloudflare-protected | 18 endpoints mapped, property data/ownership/tax records, requires paid subscription |

## Structure

```
apis/
  automotive/
    autotempest/        # Full API access (HMAC token auth cracked)
    cargurus/           # Endpoints mapped, Cloudflare-protected
  real-estate/
    zillow/             # Autocomplete works, search PerimeterX-protected
    redfin/             # Stingray API, search + CSV export work, no auth needed
    realtor/            # 10 endpoints, GraphQL API, Kasada bot protection
    loopnet/            # Commercial RE, Akamai Bot Manager blocks all access
    crexi/              # 16 endpoints, Cloudflare-protected
    propertyshark/      # 18 endpoints, Cloudflare + paid subscription required
```

## How These Are Built

Each client is created by:

1. Navigating to the target site with a headless browser
2. Injecting fetch/XHR interceptors to capture all API calls
3. Analyzing JavaScript bundles for auth secrets and token generation
4. Reverse-engineering the request signing/authentication
5. Building and testing a standalone Python client

## Disclaimer

These are unofficial clients for educational and research purposes. Internal APIs may change without notice. Use responsibly.
