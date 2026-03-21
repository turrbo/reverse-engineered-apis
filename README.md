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

## Structure

```
apis/
  automotive/
    autotempest/        # Full API access (HMAC token auth cracked)
    cargurus/           # Endpoints mapped, Cloudflare-protected
  real-estate/
    zillow/             # Autocomplete works, search PerimeterX-protected
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
