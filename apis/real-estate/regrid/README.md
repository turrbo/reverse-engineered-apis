# Regrid

Reverse-engineered API client for [Regrid](https://app.regrid.com) (formerly Loveland Technologies) -- the largest nationwide parcel data platform covering 155M+ US parcels.

## Overview

Regrid provides property/parcel data including ownership, valuations, zoning, structure details, tax information, and parcel geometry for virtually every property in the United States. The platform uses a Rails backend with Mapbox GL maps and a custom tile server.

## Endpoints Discovered

### App Server (app.regrid.com)

| Endpoint | Method | Auth | Description |
|---|---|---|---|
| `/search.json` | GET | No | Address/parcel search (autocomplete) |
| `/search/places.json` | GET | No | Place-only search (cities, counties) |
| `/search/groups.json` | GET | No | Organization/group search |
| `/search/point.json` | GET | No | Reverse geocode by lat/lng |
| `/{path}.json` | GET | Session | **Property detail lookup** (consumes quota) |
| `/users/lookup_limits.json` | GET | Session | Check remaining lookups |
| `/{path}/boundaries.json` | GET | No | Region boundaries + tile config |
| `/{path}/filters.json` | GET | No | Available filter fields for region |
| `/{path}/colors.json` | GET | No | Thematic color map data |
| `/templates.json` | GET | No | Handlebars UI templates |
| `/preferences.json` | GET | Auth | User preferences |
| `/profile.json` | GET | Auth | User profile + usage stats |
| `/profile/follows.json` | GET | Auth | Followed properties |
| `/users/renew_jwt.json` | GET | Auth | Refresh JWT token |
| `/{path}/streetside.jpg` | GET | Auth | Street-level property image |
| `/{path}/blexts.json` | GET | Session | Custom parcel data extensions |
| `/{path}/stats.json` | GET | Session | Region statistics |
| `/sources.json` | GET | No | Data source listing |

### Tile Server (tiles.regrid.com)

| Endpoint | Method | Auth | Description |
|---|---|---|---|
| `/api/v1/parcels` | GET | No | TileJSON config (base parcel layer) |
| `/api/v1/parcels/{z}/{x}/{y}.png` | GET | No | Parcel PNG raster tiles |
| `/api/v1/parcels/{z}/{x}/{y}.json` | GET | No | UTFGrid interactive tiles |
| `/api/v1/parcels/{z}/{x}/{y}.mvt` | GET | No | MVT vector tiles |
| `/api/v1/sources` | POST | No | Create filtered tile layer (returns hash) |
| `/api/v1/sources/layers/{hash}/{z}/{x}/{y}.{fmt}` | GET | No | Filtered layer tiles |
| `/api/v1/static/fema/{z}/{x}/{y}.mvt` | GET | Token | FEMA flood zone overlay |
| `/api/v1/static/wetlands/{z}/{x}/{y}.mvt` | GET | Token | National wetlands overlay |
| `/api/v1/static/us_contours/{z}/{x}/{y}.mvt` | GET | Token | USGS elevation contours |
| `/api/v1/static/esri_enrichments/{z}/{x}/{y}.mvt` | GET | Token | Esri demographic data |

## Authentication

| Tier | Lookups/Day | Method |
|---|---|---|
| Anonymous | 5 | Session cookie only |
| Free Starter | 25 | Email/password login |
| Pro | 1,000 | Paid subscription |
| Team | 2,000 | Paid subscription |

- **Session cookie**: `_session_id` (HttpOnly, 7-day expiry) -- obtained automatically on first visit
- **CSRF token**: `<meta name="csrf-token">` -- required for POST/PUT/DELETE
- **JWT token**: `window.data.jwt` -- for tile server and dimensions API (Pro/Team)
- **Tile token**: `window.data.tile_token` -- for premium overlay layers (Pro/Team)

Rate limits are tracked server-side by session cookie. Each property detail view consumes 1 lookup. Search, boundary, filter, tile, and color endpoints are **unlimited** and do not consume lookups.

## Path Format

Regrid uses hierarchical URL paths for geographic navigation:

```
/us/{state}/{county}/{city}/{parcel_id}
```

Examples:
- `/us/nh/merrimack/hooksett/97126` -- specific parcel
- `/us/nh/merrimack/hooksett` -- city
- `/us/nh/merrimack` -- county
- `/us/nh` -- state

## Data Coverage

- **155M+ parcels** across all US states and territories
- **Canada coverage** available (path prefix `/ca/`)
- **118+ fields per parcel** including:
  - Owner name, mailing address
  - Parcel address, coordinates
  - Land value, improvement value, total value
  - Year built, rooms, bathrooms, structure style
  - Zoning code, use code/description
  - Lot acreage, building square footage
  - Tax year, assessed values
  - Census tract, block, ZCTA
  - School districts
  - FEMA flood zones (premium)
  - Building footprint data (premium)
  - Delivery point validation (premium)
  - LBCS land use codes (premium)

## Usage

```python
from client import RegridClient

client = RegridClient()

# Search (unlimited, free)
results = client.search("1234 Hooksett Rd Hooksett NH")
for r in results:
    print(f"{r.headline} ({r.context})")

# Property detail (consumes 1 lookup)
parcel = client.get_property(results[0].path)
print(f"Owner: {parcel.fields.get('owner')}")
print(f"Value: ${parcel.fields.get('parval'):,.0f}")
print(f"Year built: {parcel.fields.get('yearbuilt')}")

# Check remaining lookups
limits = client.get_lookup_limits()
print(f"Remaining: {limits.remaining}/{limits.total}")

# Get region filters (unlimited)
filters = client.get_filters("/us/nh/merrimack")
for f in filters[:5]:
    print(f"  {f.key}: {f.label}")

# Create a filtered map layer (unlimited)
layer = client.create_filtered_layer({"owner": "Smith"})
print(f"Layer: {layer.png_template}")

# Login for higher limits (25/day free)
client = RegridClient(email="you@example.com", password="yourpass")
```

## Key Technical Details

- **Framework**: Ruby on Rails backend, React + Mapbox GL JS frontend
- **Tile server**: Custom Node.js server at tiles.regrid.com with TileJSON, PNG, UTFGrid, and MVT
- **Filtered layers**: POST to `/api/v1/sources` with field filters generates a deterministic SHA1 hash that identifies the filtered tile layer -- you can cache and reuse these URLs
- **CORS**: Tile server allows all origins (`Access-Control-Allow-Origin: *`)
- **Data freshness**: `metadata.table_updated` shows when the county dataset was last refreshed
- **Parcel IDs**: Internal numeric IDs (e.g., 97126) within each city, not globally unique
- **Geometry**: GeoJSON Polygon/MultiPolygon in WGS84 (EPSG:4326)
