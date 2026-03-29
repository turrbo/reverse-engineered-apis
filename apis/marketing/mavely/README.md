# Mavely Creators Platform

Reverse-engineered API client for [Mavely](https://creators.joinmavely.com), the influencer/creator affiliate marketing platform (a Later company).

## Architecture

| Component | URL | Auth |
|---|---|---|
| GraphQL API | `https://mavely.live/api/graphql` | Bearer JWT + client headers |
| Auth (Auth0) | `https://mavely.us.auth0.com/oauth/token` | Resource Owner Password Grant |
| Feature Flags | `https://unleash-edge.mavely.live/api/frontend` | Public client key |
| Frontend | `https://creators.joinmavely.com` | NextAuth sessions |

### Authentication Flow

1. **Auth0 ROPC** (`grant_type: password`) with client ID `PItSrEo35MYmLjhY6wJp8sCQAQRRWYxr`
2. Returns JWT access token (RS256, 2.5hr TTL), refresh token, and ID token
3. JWT used as `Authorization: Bearer <token>` for all GraphQL requests
4. Required custom headers: `client-name`, `client-version`, `client-revision`

### GraphQL API

Single endpoint at `https://mavely.live/api/graphql` serving 84 operations:

- **43 queries**: brands, links, analytics, earnings, promotions, shop, account
- **24 mutations**: create/update/delete for links, folders, shop, social platforms
- Introspection disabled (Apollo Server)
- Relay-style pagination (`first`/`skip`/`after`, `pageInfo.hasNextPage`)

## Capabilities

| Feature | Operations | Notes |
|---|---|---|
| **Brands** | `brandsConnection`, `brand`, `allBrands`, `trendingBrands`, `favoriteBrands`, `categories2` | 1000+ affiliate brands, search by name/category, commission rates |
| **Affiliate Links** | `affiliateLinks`, `createAffiliateLink`, `deleteAffiliateLink`, link folders | Create tracked `mavely.app.link` short URLs from any product URL |
| **Analytics** | `MetricsTotals`, `MetricsTimeSeries`, `MetricsByEntity` (Brand/Link/TrafficSource) | Clicks, sales, commission, conversion; date range filtering (`cstDateStr_gte/lte`) |
| **Earnings** | `balance`, `getPayoutStatements`, `salesBonusLevels`, `referralStats` | Payout history, 20-tier bonus structure, referral tracking |
| **Promotions** | `promotionsList`, `featuredPromotions` | Active brand deals with dates and URLs |
| **Shop** | `myShop`, `shopPages`, `shopPosts`, CRUD mutations | Creator storefronts with pages and product posts |
| **Account** | `me`, `updateUser2`, social platforms, sub-accounts, URL shorteners | Full profile management |
| **Feature Flags** | Unleash frontend API | 9 flags including fraud detection config |

## Usage

```python
from mavely_client import MavelyClient

client = MavelyClient()
client.login("email@example.com", "password")

# Browse 1000+ affiliate brands
brands = client.get_brands(first=20, search="Nike")
for edge in brands["edges"]:
    b = edge["node"]
    print(f"{b['name']}: {b['commissionRate']}% commission")

# Create a tracked affiliate link
link = client.create_affiliate_link("https://www.target.com/p/some-product")
print(link["link"])  # https://mavely.app.link/...

# Get analytics
stats = client.get_analytics_totals("2026-03-01", "2026-03-29")
print(f"Commission: ${stats['metrics']['commission']:.2f}")

# Daily time series
daily = client.get_analytics_time_series("2026-03-01", "2026-03-29")
for day in daily:
    print(f"{day['cstDateStr']}: {day['metrics']['clicksCount']} clicks")

# Get active promotions
promos = client.get_promotions(first=10)
for edge in promos["edges"]:
    p = edge["node"]
    print(f"[{p['brand']['name']}] {p['title']}")

# Manage favorite brands
client.favorite_brand("clfbb7str006e0914b0brc1v6")
fav_ids = client.get_favorite_brand_ids()
```

## Auth0 Configuration

| Parameter | Value |
|---|---|
| Domain | `mavely.us.auth0.com` |
| Client ID | `PItSrEo35MYmLjhY6wJp8sCQAQRRWYxr` |
| Audience | `https://auth.mave.ly/` |
| Grant Type | `password` (ROPC) |
| Scopes | `openid profile email offline_access` |
| Token TTL | 9000s (2.5 hours) |
| Key ID | `cDeYqsHtTAzVJIE90H1UX` (RS256) |

## Required Headers

```
client-name: @mavely/creator-app
client-version: 1.6.5
client-revision: 418e5810
Authorization: Bearer <jwt>
Content-Type: application/json
User-Agent: Mozilla/5.0 ...
```

## Rate Limits

No rate limiting observed during testing. The API is a standard Apollo GraphQL server.

## Dependencies

Python 3.7+ with stdlib only (`urllib`, `json`, `base64`). No third-party packages required.
