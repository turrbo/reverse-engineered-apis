# Reverse-Engineered APIs

Collection of unofficial API clients built by reverse-engineering websites' hidden/internal endpoints.

## APIs

| Site | Directory | Description |
|---|---|---|
| [AutoTempest](apis/autotempest/) | `apis/autotempest/` | Car listings across 10+ sources (eBay, Cars.com, Carvana, CarMax, etc.) |
| [CarGurus](apis/cargurus/) | `apis/cargurus/` | Vehicle search, pricing, dealer info, instant market value (Cloudflare-protected) |
| [Zillow](apis/zillow/) | `apis/zillow/` | Property autocomplete, geocoding, ZPID lookup, region search (PerimeterX-protected) |

## How These Are Built

Each client is created by:

1. Navigating to the target site with a headless browser
2. Injecting fetch/XHR interceptors to capture all API calls
3. Analyzing JavaScript bundles for auth secrets and token generation
4. Reverse-engineering the request signing/authentication
5. Building and testing a standalone Python client

## Structure

```
apis/
  autotempest/        # Full API access (HMAC token auth cracked)
  cargurus/           # Endpoints mapped, Cloudflare-protected
  zillow/             # Autocomplete works, search PerimeterX-protected
```

## Disclaimer

These are unofficial clients for educational and research purposes. Internal APIs may change without notice. Use responsibly.
