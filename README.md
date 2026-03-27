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
| [Sociamonials](apis/marketing/sociamonials/) | `apis/marketing/sociamonials/` | Full access | Social media post creation, scheduling, queue, drafts, analytics, CRM (session auth, login required) |
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

## Jobs

| Site | Directory | Status | Description |
|---|---|---|---|
| [Canyon](apis/jobs/canyon/) | `apis/jobs/canyon/` | Full access | GraphQL API -- 49 queries, 90 mutations, job search, AI resumes/cover letters, interview prep (Google OAuth) |

## Weather

| Site | Directory | Status | Description |
|---|---|---|---|
| [Weather.gov (NWS)](apis/weather/weather-gov/) | `apis/weather/weather-gov/` | Full access | 54 endpoints -- forecasts, alerts, stations, radar, aviation, products (no auth required) |
| [NOAA WPC](apis/weather/noaa-wpc/) | `apis/weather/noaa-wpc/` | Full access | Surface analysis, QPF, winter weather, ERO, discussions, forecast charts (no auth required) |
| [Windy.com](apis/weather/windy/) | `apis/weather/windy/` | Full access | ECMWF/GFS/NAM/ICON models, radar coverage (1000+ stations), city tiles, geolocation (custom Accept header auth) |
| [Tropical Tidbits](apis/weather/tropical-tidbits/) | `apis/weather/tropical-tidbits/` | Full access | 29 forecast models, storm tracking, soundings, satellite imagery CDN, ocean/SST analysis (no auth required) |
| [Pivotal Weather](apis/weather/pivotal-weather/) | `apis/weather/pivotal-weather/` | Partial access | 29+ models, image servers public, JSON API AWS WAF-protected (no auth for images) |
| [RainViewer](apis/weather/rainviewer/) | `apis/weather/rainviewer/` | Full access | 1016 radar stations (83 countries), satellite tiles, severe alerts, storm tracking (session token auth) |
| [Weather Underground](apis/weather/wunderground/) | `apis/weather/wunderground/` | Full access | 30+ endpoints, 250K+ PWS stations, 86 tile products, 15-day forecasts (API keys from SSR) |
| [Ventusky](apis/weather/ventusky/) | `apis/weather/ventusky/` | Full access | 17 endpoints, 38 weather models, 50+ layers, weather fronts, webcams (no auth required) |
| [SpotWX](apis/weather/spotwx/) | `apis/weather/spotwx/` | Full access | 13 gridded NWP models, multi-model point forecasts, Highcharts data parsing (no auth required) |
| [LightningMaps](apis/weather/lightningmaps/) | `apis/weather/lightningmaps/` | Full access | Real-time global lightning via WebSocket, 2000+ stations, tiles, archive (challenge-response auth cracked) |
| [College of DuPage NEXLAB](apis/weather/cod-nexlab/) | `apis/weather/cod-nexlab/` | Full access | NEXRAD radar (18+ products), GOES satellite (16 bands), 11 models, NWS warnings JSON (no auth required) |
| [OpenSnow](apis/weather/opensnow/) | `apis/weather/opensnow/` | Full access | Snow forecasts, resort data, avalanche danger, webcams, powder maps (API key from Nuxt config) |
| [Zoom Earth](apis/weather/zoom-earth/) | `apis/weather/zoom-earth/` | Full access | Satellite tiles (GOES/Himawari/MSG/MTG), radar, fires, storms (ROT-13/base64 obfuscation + HMAC sig cracked) |
| [Meteoblue](apis/weather/meteoblue/) | `apis/weather/meteoblue/` | Full access | Multimodel forecasts, ERA5T historical (1940+), air quality, maps, meteograms (API keys from JS) |
| [AerisWeather/Xweather](apis/weather/aerisweather/) | `apis/weather/aerisweather/` | Auth required | 55 endpoints -- alerts, lightning, fire, maritime, tropical, air quality, road weather (client_id/secret required) |
| [World Weather Online](apis/weather/worldweatheronline/) | `apis/weather/worldweatheronline/` | Partial access | 9 internal AJAX endpoints (no key) + 7 premium REST endpoints, historical data 2008+ (ASP.NET hidden fields) |
| [Open-Meteo](apis/weather/open-meteo/) | `apis/weather/open-meteo/` | Full access | 13 API subdomains (4 undocumented), 200+ models incl. AI, satellite data since 1983 (no auth required) |

## Design

| Site | Directory | Status | Description |
|---|---|---|---|
| [MyDesigns.io](apis/design/mydesigns/) | `apis/design/mydesigns/` | Full access | 178 endpoints -- POD products, orders, mockups, AI tools, canvas editor, shop integrations (Etsy/Shopify/Amazon/TikTok), wallets (Ory auth, login required) |

## Cameras & Webcams

| Site | Directory | Status | Description |
|---|---|---|---|
| [Windy Webcams](apis/cameras/windy-webcams/) | `apis/cameras/windy-webcams/` | Auth required | 100K+ webcams, v3 REST API, 18 categories, map clusters, player embeds (API key required) |
| [AlertWildfire](apis/cameras/alertwildfire/) | `apis/cameras/alertwildfire/` | Full access | 2,200+ wildfire/fire cameras (128 AWF + 2,072 AlertCalifornia), MJPEG timelapse, panoramic grid (Referer auth) |
| [USGS Volcano Webcams](apis/cameras/usgs-volcanocams/) | `apis/cameras/usgs-volcanocams/` | Full access | 5 API systems, 400+ cameras (HVO + AVO + CVO + YVO), HANS notice search, volcanic activity detection (no auth) |
| [NOAA Cams](apis/cameras/noaa-cams/) | `apis/cameras/noaa-cams/` | Full access | GOES satellite CDN (up to 10848x10848), 90+ BuoyCAMs, realtime + historical marine data (no auth) |
| [WeatherBug Cameras](apis/cameras/weatherbug-cams/) | `apis/cameras/weatherbug-cams/` | Full access | 13 API endpoints, cameras + traffic + weather + maps, 17 map layers (HMAC-SHA256 auth cracked) |
| [EarthCam](apis/cameras/earthcam/) | `apis/cameras/earthcam/` | Full access | 298+ landmark cameras, 12 endpoints, signed HLS streams, timelapse archives, bounding box search (no auth) |
| [Surfline](apis/cameras/surfline/) | `apis/cameras/surfline/` | Full access | 500+ surf cameras, wave/wind/tide forecasts, CDN stills + rewind clips, spot reports (Origin header auth) |
| [FAA WeatherCams](apis/cameras/faa-weathercams/) | `apis/cameras/faa-weathercams/` | Full access | 232 aviation weather cameras (Alaska-heavy), METAR/TAF data, image archives (no auth) |
| [Skiresort.info Webcams](apis/cameras/skiresort-webcams/) | `apis/cameras/skiresort-webcams/` | Full access | 5,900+ ski resort webcams, snow reports, resort metadata, multi-country coverage (no auth) |
| [SkylineWebcams](apis/cameras/skylinewebcams/) | `apis/cameras/skylinewebcams/` | Full access | Thousands of webcams, 50+ countries, HLS streams, categories (beaches/volcanoes/cities), timelapse (no auth) |
| [WebcamGalore](apis/cameras/webcamgalore/) | `apis/cameras/webcamgalore/` | Full access | 8,000+ webcams, XML bounding box API, 30 theme filters, 365-day daily archives, hourly timelapse (no auth) |
| [Foto-Webcam.eu](apis/cameras/foto-webcam/) | `apis/cameras/foto-webcam/` | Full access | 398 Alpine webcams, up to 6000x4000 resolution, PHP JSON API, historical archives, EXIF data (no auth) |
| [HDOnTap](apis/cameras/hdontap/) | `apis/cameras/hdontap/` | Full access | 203 HD streams (wildlife/scenic/beach), Wowza SecureToken HLS up to 4K, timelapse (no auth) |
| [explore.org](apis/cameras/explore-org/) | `apis/cameras/explore-org/` | Full access | 100+ wildlife/nature cameras (bears, birds, ocean), YouTube HLS streams, categories (no auth) |
| [NPS Webcams](apis/cameras/nps-webcams/) | `apis/cameras/nps-webcams/` | Full access | 290 National Park cameras + 22 air quality webcams, archive since 2005, AQ timeseries (DEMO_KEY works) |
| [DOT 511 (8 States)](apis/cameras/dot-511/) | `apis/cameras/dot-511/` | Auth required | 2,923+ DOT traffic cameras (NY/WI/PA/AK/UT/MN/VA/IA), HLS streams, unified Iteris platform (free API key) |
| [Oregon TripCheck](apis/cameras/oregon-tripcheck/) | `apis/cameras/oregon-tripcheck/` | Full access | 1,120 cameras (321 video), 221 RWIS weather stations, road conditions, travel times (no auth) |
| [WSDOT](apis/cameras/wsdot/) | `apis/cameras/wsdot/` | Full access | 1,658 cameras, RSS/KML feeds, mountain pass conditions, image URL pattern cracked (no auth for feeds) |
| [Camscape](apis/cameras/camscape/) | `apis/cameras/camscape/` | Full access | 1,325 webcams, WordPress REST + SAYT search, world map geo data, stream types (no auth) |
| [Opentopia](apis/cameras/opentopia/) | `apis/cameras/opentopia/` | Full access | 1,432+ public cameras, geographic search, random camera, categories (no auth) |

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
  jobs/
    canyon/             # Full access, GraphQL, 49 queries + 90 mutations, Google OAuth
  weather/
    weather-gov/        # Full access, 54 NWS endpoints, no auth needed
    noaa-wpc/           # Full access, surface analysis, QPF, forecasts, no auth
    windy/              # ECMWF/GFS/NAM/ICON, radar, city tiles, custom Accept header
    tropical-tidbits/   # 29 models, storms, soundings, satellite CDN, ocean analysis
    pivotal-weather/    # 29+ models, public image servers, WAF-protected JSON API
    rainviewer/         # 1016 radar stations, satellite, alerts, session token auth
    wunderground/       # 30+ endpoints, 250K+ PWS, 86 tile products, API keys from SSR
    ventusky/           # 38 models, 50+ layers, fronts, webcams, no auth
    spotwx/             # 13 NWP models, multi-model point forecasts, no auth
    lightningmaps/      # Real-time lightning WebSocket, 2000+ stations, challenge-response
    cod-nexlab/         # NEXRAD 18+ products, GOES 16 bands, 11 models, NWS warnings
    opensnow/           # Snow forecasts, resort data, avalanche, API key from Nuxt
    zoom-earth/         # Satellite GOES/Himawari/MSG, radar, fires, HMAC sig cracked
    meteoblue/          # Multimodel, ERA5T since 1940, API keys from JS bundles
    aerisweather/       # 55 endpoints, rebranded to Xweather, client_id/secret auth
    worldweatheronline/ # 9 AJAX + 7 REST endpoints, historical 2008+, ASP.NET
    open-meteo/         # 13 subdomains (4 undocumented), 200+ models, satellite data
  cameras/
    windy-webcams/      # 100K+ webcams, v3 REST API, API key required
    alertwildfire/      # 2,200+ wildfire cameras, Referer-gated S3, MJPEG timelapse
    usgs-volcanocams/   # 5 API systems, 400+ cameras, HANS notice search
    noaa-cams/          # GOES satellite CDN + 90+ BuoyCAMs, no auth
    weatherbug-cams/    # HMAC-SHA256 auth cracked, 13 endpoints, cameras + weather
    earthcam/           # 298+ cameras, signed HLS streams, timelapse, bounding box
    surfline/           # 500+ surf cams, wave/tide/wind forecasts, Origin header auth
    faa-weathercams/    # 232 aviation cameras, Alaska-heavy, METAR/TAF
    skiresort-webcams/  # 5,900+ ski webcams, snow reports, multi-country
    skylinewebcams/     # Thousands worldwide, HLS streams, 50+ countries
    webcamgalore/       # 8,000+ webcams, XML bounding box API, 365-day archive
    foto-webcam/        # 398 Alpine webcams, up to 6000x4000, PHP JSON API
    hdontap/            # 203 HD streams, Wowza SecureToken, up to 4K
    explore-org/        # 100+ wildlife cameras, YouTube HLS, categories
    nps-webcams/        # 290 NPS + 22 AQ cameras, archive since 2005
    dot-511/            # 2,923+ DOT cameras (8 states), HLS streams, free API key
    oregon-tripcheck/   # 1,120 cameras, 221 RWIS stations, road conditions
    wsdot/              # 1,658 cameras, RSS/KML feeds, mountain passes
    camscape/           # 1,325 webcams, WordPress REST, world map geo data
    opentopia/          # 1,432+ public cameras, geographic search
  design/
    mydesigns/          # Full access, 178 endpoints, Ory auth, POD platform
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
