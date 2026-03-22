# Reverse-Engineered APIs

Collection of unofficial API clients built by reverse-engineering websites' hidden/internal endpoints.

## Automotive

| Site | Directory | Status | Description |
|---|---|---|---|
| [AutoTempest](apis/automotive/autotempest/) | `apis/automotive/autotempest/` | Full access | Car listings across 10+ sources (eBay, Cars.com, Carvana, CarMax, etc.) |
| [CarGurus](apis/automotive/cargurus/) | `apis/automotive/cargurus/` | Cloudflare-protected | Vehicle search, pricing, dealer info, instant market value |
| [VinWiki](apis/automotive/vinwiki/) | `apis/automotive/vinwiki/` | Full access | Vehicle history, VIN lookup, search, vehicle feed (token auth, login required) |

## Real Estate

| Site | Directory | Status | Description |
|---|---|---|---|
| [Zillow](apis/real-estate/zillow/) | `apis/real-estate/zillow/` | Partial access | Property autocomplete, geocoding, ZPID lookup, region search |
| [Redfin](apis/real-estate/redfin/) | `apis/real-estate/redfin/` | Partial access | Stingray API -- property search, CSV export, region data (no auth required) |
| [Realtor.com](apis/real-estate/realtor/) | `apis/real-estate/realtor/` | Kasada-protected | 10 endpoints mapped, GraphQL API, requires browser automation |
| [LoopNet](apis/real-estate/loopnet/) | `apis/real-estate/loopnet/` | Akamai-protected | Commercial real estate, endpoints mapped but blocked by Akamai Bot Manager |
| [Crexi](apis/real-estate/crexi/) | `apis/real-estate/crexi/` | Cloudflare-protected | 16 commercial real estate endpoints, property search, auctions, market data |
| [PropertyShark](apis/real-estate/propertyshark/) | `apis/real-estate/propertyshark/` | Cloudflare-protected | 18 endpoints mapped, property data/ownership/tax records, requires paid subscription |

## Entertainment

| Site | Directory | Status | Description |
|---|---|---|---|
| [Artistly AI](apis/entertainment/artistly/) | `apis/entertainment/artistly/` | Full access | AI art generation -- T-shirt designs, storybooks, image stylization, 81+ styles (login required) |

## Technology

| Site | Directory | Status | Description |
|---|---|---|---|
| [Product Hunt](apis/technology/producthunt/) | `apis/technology/producthunt/` | Full access | GraphQL v2 API -- daily products, search, topics, collections, users (OAuth2 required) |

## Marketing

| Site | Directory | Status | Description |
|---|---|---|---|
| [Sociamonials](apis/marketing/sociamonials/) | `apis/marketing/sociamonials/` | Full access | Social media scheduling, campaigns, analytics, CRM, AI writer (session auth, login required) |
| [NeuronWriter](apis/marketing/neuronwriter/) | `apis/marketing/neuronwriter/` | Auth required | SEO content optimization, SERP analysis, NLP terms, competitors (API key + session auth) |
| [Taja AI](apis/marketing/taja/) | `apis/marketing/taja/` | Auth required | YouTube video optimization, titles, descriptions, tags, thumbnails (login required) |
| [Skimming AI](apis/marketing/skimming/) | `apis/marketing/skimming/` | Auth required | Redirects to NeuronWriter -- same CONTADU platform, content summarization |

## Productivity

| Site | Directory | Status | Description |
|---|---|---|---|
| [Recall AI](apis/productivity/getrecall/) | `apis/productivity/getrecall/` | Full access | 50+ endpoints -- sync, AI summaries, chat, quiz generation, entity extraction, scraping (Firebase/Google auth) |

## Education

| Site | Directory | Status | Description |
|---|---|---|---|
| [Anna's Archive](apis/education/annas-archive/) | `apis/education/annas-archive/` | Full access | Book/publication search, ISBN/DOI lookup, metadata extraction (no auth required) |

## Sports

| Site | Directory | Status | Description |
|---|---|---|---|
| [Formula 1](apis/sports/formula1/) | `apis/sports/formula1/` | Full access | OpenF1 API -- sessions, drivers, lap times, telemetry, pit stops, weather (no auth required) |

## Structure

```
apis/
  automotive/
    autotempest/        # Full API access (HMAC token auth cracked)
    cargurus/           # Endpoints mapped, Cloudflare-protected
    vinwiki/            # Full access, REST API, token auth
  real-estate/
    zillow/             # Autocomplete works, search PerimeterX-protected
    redfin/             # Stingray API, search + CSV export work, no auth needed
    realtor/            # 10 endpoints, GraphQL API, Kasada bot protection
    loopnet/            # Commercial RE, Akamai Bot Manager blocks all access
    crexi/              # 16 endpoints, Cloudflare-protected
    propertyshark/      # 18 endpoints, Cloudflare + paid subscription required
  entertainment/
    artistly/           # Full access, login-based auth (Laravel/CSRF)
  technology/
    producthunt/        # Full access, GraphQL v2, OAuth2 required
  marketing/
    sociamonials/       # Full access, PHP session auth
    neuronwriter/       # SEO tool, API key + session auth (needs valid credentials)
    taja/               # YouTube optimizer, login required (needs valid credentials)
    skimming/           # Redirects to NeuronWriter (same platform)
  productivity/
    getrecall/          # Full access, 50+ endpoints, Firebase auth
  education/
    annas-archive/      # Full access, no auth, HTML parsing
  sports/
    formula1/           # Full access, OpenF1 API, no auth needed
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
