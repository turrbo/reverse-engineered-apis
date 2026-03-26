# MyDesigns.io API Client

Reverse-engineered internal API client for [MyDesigns.io](https://mydesigns.io) — the all-in-one automation platform for Print on Demand and Digital product sellers.

---

## Overview

MyDesigns.io does not currently publish official API documentation (it is "coming soon"), but the application exposes a fully functional internal REST API at `https://api.mydesigns.io`. This client was built by reverse engineering the frontend JavaScript bundles and monitoring network traffic.

### Key Facts

| Property | Value |
|---|---|
| API Base URL | `https://api.mydesigns.io` |
| Auth Service | `https://accounts.mydesigns.io` (Ory identity platform) |
| Auth Methods | Session cookies OR Personal Access Token (Bearer) |
| Content Type | `application/json` |
| Frontend | Vue.js SPA with Vite bundler |

---

## Authentication

### Method 1: Session Cookies (Login Flow)

MyDesigns uses [Ory](https://www.ory.sh/) as its identity provider at `accounts.mydesigns.io`. The login is a two-step "identifier_first" flow:

1. POST the user's email to get the password prompt
2. POST the password to complete authentication

On success, Ory sets session cookies that authenticate all subsequent requests to `api.mydesigns.io`.

```python
from mydesigns_client import MyDesignsClient

client = MyDesignsClient()
client.login("your_email@example.com", "your_password")

# Now all API calls are authenticated
me = client.get_me()
```

#### Ory Login Flow Details

```
GET  https://accounts.mydesigns.io/self-service/login/browser
     ?return_to=https%3A%2F%2Fmydesigns.io%2Fapp%2Fdashboard

GET  https://accounts.mydesigns.io/self-service/login/flows?id=<flow_id>

POST https://accounts.mydesigns.io/self-service/login?flow=<flow_id>
     {"csrf_token": "<token>", "method": "identifier_first", "identifier": "<email>"}

POST https://accounts.mydesigns.io/self-service/login?flow=<flow_id>
     {"csrf_token": "<new_token>", "method": "password", "identifier": "<email>", "password": "<pass>"}
```

### Method 2: Personal Access Token (Bearer)

More suitable for automated/headless usage. Generate a PAT via the UI (`Settings > Tokens`) or via the API:

```python
client = MyDesignsClient()
client.login("your_email@example.com", "your_password")

# Create a PAT
pat = client.create_personal_access_token("my-automation-token")
bearer_token = pat["bearer"]  # Save this securely

# Later, use without logging in
client2 = MyDesignsClient(bearer_token=bearer_token)
me = client2.get_me()
```

#### Bearer Token Format

The bearer token is a **base64-encoded JSON** object:

```
base64({"id": <int>, "value": "<string>"})
```

Usage:
```
Authorization: Bearer eyJpZCI6MTIzNCwidmFsdWUiOiJ4eHh4In0=
```

#### Verify Current Session

```
GET https://accounts.mydesigns.io/sessions/whoami
```

---

## Installation

```bash
pip install requests
```

No other external dependencies required.

---

## Quick Start

```python
from mydesigns_client import MyDesignsClient

client = MyDesignsClient()
client.login("your_email@example.com", "your_password")

# Get user profile
me = client.get_me()
print(f"Hello, {me['name']}!")
print(f"Credits: {me['credits']}")
print(f"Plan: {me['subscriptionTier']['code']}")

# Get connected shops
shops = client.get_provider_users()
for shop in shops:
    print(f"  - {shop.get('providerName')}: {shop.get('shopName')}")

# Get recent orders
orders = client.get_recent_orders(days_ago=30)
print(f"Orders in last 30 days: {len(orders)}")

# Get top sold listings
top = client.get_top_sold_publications(days_ago=30)
for item in top[:5]:
    print(f"  {item.get('title')}: {item.get('sales')} sales")
```

---

## API Reference

### Authentication Endpoints

| Method | Path | Description |
|---|---|---|
| GET | `/self-service/login/browser` | Initiate Ory login flow |
| GET | `/self-service/login/flows?id=<flow_id>` | Get flow details and CSRF token |
| POST | `/self-service/login?flow=<flow_id>` | Submit credentials (step 1: email, step 2: password) |
| GET | `/self-service/logout/browser` | Logout and invalidate session |
| GET | `/sessions/whoami` | Get current session info |

All above endpoints are on `https://accounts.mydesigns.io`.

---

### Users

| Method | Path | Description |
|---|---|---|
| GET | `/users/me` | Get current user profile |
| PUT | `/users/me/update` | Update name/settings |
| PUT | `/users/me/update-address` | Update shipping address |
| GET | `/users/me/credits` | Get credit balance |
| GET | `/users/me/invitation-link` | Get referral link |
| POST | `/users/me/track-onboarding-event` | Track onboarding progress |
| GET | `/users/info?ids=<id1>&ids=<id2>` | Get user info by IDs |
| GET | `/users/hub/negotiate` | SignalR hub negotiation (real-time events) |

### Personal Access Tokens

| Method | Path | Description |
|---|---|---|
| GET | `/users/me/personal-access-tokens` | List all PATs |
| POST | `/users/me/personal-access-tokens` | Create new PAT (body: `{"name": "..."}`) |
| DELETE | `/users/me/personal-access-tokens/{id}` | Revoke a PAT |

**Note:** Token values are only returned once on creation and are never stored by MyDesigns for security reasons.

### Designs & Listings

| Method | Path | Description |
|---|---|---|
| GET | `/categories` | Get listing categories/collections |
| GET | `/designs?categoryId=<id>` | Get designs in a category |
| GET | `/templates/{id}` | Get a listing template |
| GET | `/listings/imported-designs` | Get imported designs |
| GET | `/jobs?marker=<id>` | Get background job statuses |
| GET | `/tutorials` | Get tutorials list |
| POST | `/designs/vectorize/create-preview` | Vectorize a design |

### Products

| Method | Path | Description |
|---|---|---|
| GET | `/products` | List all products |
| GET | `/products/{id}` | Get a single product |
| DELETE | `/products/{id}` | Delete a product |
| POST | `/products/delete` | Bulk delete products |
| GET | `/products/{id}/files` | Get product files |
| GET | `/products/{id}/items` | Get product variants |
| GET | `/products/{id}/print-files` | Get print files |
| POST | `/products/{id}/regenerate-mockups` | Regenerate mockups |
| POST | `/products/{id}/resync` | Resync with source |
| GET | `/products/{id}/status` | Get product status |
| GET | `/products/bulk/{bulkId}` | Get bulk product group |
| POST | `/products/bulk` | Create bulk product |
| POST | `/products/bulk/{bulkId}/clone` | Clone bulk product |
| POST | `/products/bulk/delete` | Delete bulk products |

### Orders

| Method | Path | Description |
|---|---|---|
| GET | `/orders` | List all orders |
| GET | `/orders/{id}` | Get a single order |
| GET | `/orders/external` | Get external/marketplace orders |
| GET | `/orders/recent?daysAgo=30&providerId=0&ordersType=all` | Get recent orders |
| GET | `/orders/status?providerUserId=0&status=CREATED&page=1` | Orders by status |
| GET | `/orders/top-sold-publications?daysAgo=30` | Top sold publications |
| GET | `/orders/{id}/thumbnail` | Get order thumbnail |
| POST | `/orders/{id}/approve` | Approve an order |
| POST | `/orders/{id}/cancel` | Cancel an order |
| POST | `/orders/{id}/note` | Add a note to an order |
| POST | `/orders/{id}/retry-charge` | Retry failed payment |
| POST | `/orders/calculate-shipping` | Calculate shipping cost |
| POST | `/orders/export` | Export orders as CSV |
| POST | `/orders/manual` | Create a manual order |

**Order Status Values:**
- `CREATED` - Order placed, awaiting action
- `FAILED_TO_CHARGE` - Payment failed

### Publications

| Method | Path | Description |
|---|---|---|
| GET | `/publications?pageIndex=1` | List all publications |
| POST | `/publications/check-publications-status` | Check live status |
| POST | `/publications/delete-publications` | Bulk delete publications |
| GET | `/publications/groups` | Get publication groups |
| GET | `/publications/pod/{id}/preview` | POD publication preview |
| GET | `/publications/digital/{id}/preview` | Digital publication preview |
| GET | `/publications/pod/{id}/print-areas` | POD print areas |
| GET | `/publications/user-profiles` | Get shop-specific metadata profiles |
| GET | `/publications/user-profile/{id}` | Get a specific profile |
| PUT | `/publications/user-profile/{id}` | Update a profile |
| GET | `/publications/zip-file/{id}` | Get zip file for a publication |

### Providers / Connected Shops

| Method | Path | Description |
|---|---|---|
| GET | `/providers` | List all provider integrations |
| GET | `/providers/provider-users` | List connected shop accounts |
| GET | `/providers/payment-method/{providerUserId}` | Get shop payment method |
| GET | `/providers/shop-address/{providerUserId}` | Get shop address |
| GET | `/providers/self-fulfillment/{providerUserId}` | Get self-fulfillment settings |

### Notifications

| Method | Path | Description |
|---|---|---|
| GET | `/notifications/deliveries` | Get notification inbox |
| POST | `/notifications/read` | Mark notifications as read |
| GET | `/notifications/preferences` | Get notification preferences |
| PUT | `/notifications/preferences` | Update preferences |

---

### Integrations: Etsy

| Method | Path | Description |
|---|---|---|
| GET | `/integrations/etsy/seller-taxonomies` | Get Etsy product categories |
| GET | `/integrations/etsy/shop/shipping-profiles?providerUserId=<id>` | Get shipping profiles |
| GET | `/integrations/etsy/default-shipping-profile` | Get default shipping profile |
| GET | `/integrations/etsy/shop/sections?providerUserId=<id>` | Get shop sections |
| POST | `/integrations/etsy/connect` | Connect Etsy shop |
| DELETE | `/integrations/etsy/disconnect/{providerUserId}` | Disconnect Etsy shop |
| POST | `/integrations/etsy/publish/pod` | Publish POD product |
| POST | `/integrations/etsy/publish/digital` | Publish digital product |
| POST | `/integrations/etsy/publish/pod/from-product` | Publish from existing product |
| POST | `/integrations/etsy/listings/import` | Import existing Etsy listings |
| GET | `/integrations/etsy/listing/variants` | Get listing variants |
| POST | `/integrations/etsy/listing/update-variants` | Update listing variants |
| POST | `/integrations/etsy/validate/fields` | Validate listing fields |
| POST | `/integrations/etsy/validate/images` | Validate images |
| GET | `/integrations/etsy/production-partners/{providerUserId}` | Get production partners |

### Integrations: Shopify

| Method | Path | Description |
|---|---|---|
| POST | `/integrations/shopify/app/connect` | Connect Shopify store |
| POST | `/integrations/shopify/app/uninstall/{providerUserId}` | Disconnect Shopify |
| GET | `/integrations/shopify/categories` | Get Shopify categories |
| GET | `/integrations/shopify/shop/collections?providerUserId=<id>` | Get collections |
| GET | `/integrations/shopify/shop/delivery-profiles?providerUserId=<id>` | Get delivery profiles |
| POST | `/integrations/shopify/publish/pod` | Publish POD product |
| POST | `/integrations/shopify/publish/digital` | Publish digital product |
| POST | `/integrations/shopify/listings/import` | Import existing products |
| POST | `/integrations/shopify/validate/fields` | Validate fields |
| POST | `/integrations/shopify/validate/images` | Validate images |
| POST | `/integrations/shopify/{providerUserId}/listings/update` | Update all listings |

### Integrations: WooCommerce

| Method | Path | Description |
|---|---|---|
| POST | `/integrations/woocommerce/connect` | Connect WooCommerce store |
| DELETE | `/integrations/woocommerce/disconnect/{providerUserId}` | Disconnect |
| GET | `/integrations/woocommerce/categories` | Get product categories |
| POST | `/integrations/woocommerce/publish/pod` | Publish POD product |
| POST | `/integrations/woocommerce/publish/digital` | Publish digital product |
| POST | `/integrations/woocommerce/validate/fields` | Validate fields |
| GET | `/integrations/woocommerce/sync-shipping-profiles/{providerUserId}` | Sync shipping |

### Integrations: TikTok Shops

| Method | Path | Description |
|---|---|---|
| GET | `/integrations/tiktokshops/auth-url` | Get OAuth URL |
| DELETE | `/integrations/tiktokshops/disconnect/{providerUserId}` | Disconnect |
| POST | `/integrations/tiktokshops/publish` | Publish product |
| GET | `/integrations/tiktokshops/taxonomies?providerUserId=<id>` | Get categories |
| GET | `/integrations/tiktokshops/brands` | Get brands |
| GET | `/integrations/tiktokshops/warehouses/{providerUserId}` | Get warehouses |
| POST | `/integrations/tiktokshops/listings/import` | Import listings |
| POST | `/integrations/tiktokshops/validate/fields` | Validate fields |
| GET | `/integrations/tiktokshops/listing/variants` | Get variants |
| POST | `/integrations/tiktokshops/listing/toggle-sellability` | Toggle listing active |

### Integrations: Amazon

| Method | Path | Description |
|---|---|---|
| GET | `/integrations/amazon/auth-uri/{marketplace}` | Get OAuth URI |
| DELETE | `/integrations/amazon/disconnect/{providerUserId}` | Disconnect |
| POST | `/integrations/amazon/publish` | Publish product |
| POST | `/integrations/amazon/validate/fields` | Validate fields |
| POST | `/integrations/amazon/validate/images` | Validate images |

### Integrations: Printify

| Method | Path | Description |
|---|---|---|
| POST | `/integrations/printify/connect` | Connect Printify |
| DELETE | `/integrations/printify/disconnect/{printPartnerUserId}` | Disconnect |
| GET | `/integrations/printify/blueprints` | Get product blueprints |
| GET | `/integrations/printify/blueprints/{blueprintId}` | Get specific blueprint |
| POST | `/integrations/printify/calculate-cost` | Calculate production cost |
| POST | `/integrations/printify/generate-mockups` | Generate mockups |

### Canvas Editor

| Method | Path | Description |
|---|---|---|
| GET | `/integrations/canvas/size-presets` | Get canvas size presets |
| POST | `/integrations/canvas/size-presets` | Create size preset |
| DELETE | `/integrations/canvas/size-presets/{id}` | Delete size preset |
| GET | `/integrations/canvas/fonts` | Get available fonts |
| GET | `/integrations/canvas/fonts/custom` | Get custom fonts |
| POST | `/integrations/canvas/fonts/{id}/favorite` | Toggle font favorite |
| GET | `/integrations/canvas/illustrations` | Get illustration assets |
| GET | `/integrations/canvas/illustration-categories` | Get illustration categories |
| POST | `/integrations/canvas/render-scene` | Render canvas to image |
| POST | `/integrations/canvas/store` | Save canvas as design |
| POST | `/integrations/canvas/bulk-edit-listings` | Bulk edit via canvas |

### Mockups

| Method | Path | Description |
|---|---|---|
| GET | `/integrations/mockups?sort=RECENT&official=false&enabledOnly=false&validOnly=false&page=1` | List mockup templates |
| GET | `/integrations/mockups/{mockupId}` | Get a single mockup |
| GET | `/integrations/mockups/categories` | Get mockup categories |
| GET | `/integrations/mockups/profiles` | Get saved mockup profiles |
| POST | `/integrations/mockups/{mockupId}/generate-preview` | Generate mockup preview |
| POST | `/integrations/mockups/{mockupId}/favorite` | Toggle favorite |
| GET | `/integrations/mockups/{mockupId}/download` | Get download URL |
| POST | `/integrations/mockups/multiple` | Generate multiple mockups at once |
| GET | `/integrations/mockups/pod-product-type/{podProductTypeId}` | Get mockup for product type |

### Dream AI

| Method | Path | Description |
|---|---|---|
| GET | `/integrations/dreamer/dream-images?keywords=&pageIndex=1` | Get AI-generated images |

### AI Tools

| Method | Path | Description |
|---|---|---|
| POST | `/integrations/vision/analyze-image` | AI image analysis (tags, title, description) |
| POST | `/integrations/vision/analyze-image-publish` | Analyze and apply to listing |
| POST | `/integrations/translate` | Translate listing text |
| GET | `/integrations/trademarks/check-text?text=<text>` | Check trademark conflicts |
| POST | `/integrations/trademarks/bulk-check` | Bulk trademark check |
| GET | `/integrations/pixabay/images?q=<query>` | Search Pixabay images |
| POST | `/integrations/pixabay/images/{id}/store` | Import Pixabay image |
| POST | `/integrations/bulk-edit` | Bulk edit multiple listings |

### Files & Assets

| Method | Path | Description |
|---|---|---|
| POST | `/files/sign` | Get pre-signed upload URL |
| GET | `/files/{fileGuid}` | Get file info |
| DELETE | `/files/{fileGuid}` | Delete a file |
| GET | `/assets/folders` | Get asset storage folders |
| GET | `/image-patterns` | Get image pattern assets |
| GET | `/color-profiles` | Get color profiles |
| POST | `/color-profiles/add` | Add color profile |

### POD Products

| Method | Path | Description |
|---|---|---|
| GET | `/pod/products/types` | Get all POD product types |
| GET | `/pod/products/variants` | Get POD product variants |
| GET | `/pod/products/print-areas` | Get print area configurations |

### Print Partners

| Method | Path | Description |
|---|---|---|
| GET | `/print-partners/print-partner-users/{userId}` | Get print partner connections |
| GET | `/print-partners/cost-analysis/{partnerCode}` | Get cost analysis |
| GET | `/print-partners/cost-analysis/{partnerCode}/saved` | Get saved cost analysis |
| GET | `/print-partners/cost-analysis/{partnerCode}/shipping` | Get shipping cost analysis |

### Store (MyDesigns Marketplace)

| Method | Path | Description |
|---|---|---|
| GET | `/stores/me` | Get current user's store |
| GET | `/stores/{slug}/public` | Get public store by slug |
| GET | `/stores/{slug}/publications` | Get store's publications |
| GET | `/stores/me/stripe/status` | Get Stripe payout status |
| GET | `/stores/me/stripe/dashboard` | Get Stripe dashboard link |
| POST | `/stores/publish/pod` | Publish to MyDesigns store |

### Wallets

| Method | Path | Description |
|---|---|---|
| GET | `/wallets/me/balance` | Get wallet balance |
| GET | `/wallets/me/wallet-transactions` | Get transaction history |
| GET | `/wallets/me/auto-topup` | Get auto top-up settings |
| POST | `/wallets/me/wallet-topup/checkout` | Top up wallet via checkout |
| POST | `/wallets/me/wallet-topup/bank-intent` | Top up via bank |

### Reports

| Method | Path | Description |
|---|---|---|
| GET | `/reports/preferences` | Get report preferences |
| PUT | `/reports/preferences` | Update report preferences |

### Support / Community

| Method | Path | Description |
|---|---|---|
| GET | `/support/discussions?pageIndex=1&status=OPENED` | List discussions |
| GET | `/support/discussions/{id}` | Get single discussion |
| POST | `/support/discussions` | Create new discussion |
| POST | `/support/discussions/{id}/comments` | Add comment |
| GET | `/support/circle/posts?circlePostGroup=news` | Get community posts |
| GET | `/support/circle/events` | Get community events |
| GET | `/support/intercom/hmac` | Get Intercom chat HMAC |

### Subscriptions / Payments

| Method | Path | Description |
|---|---|---|
| GET | `/integrations/pks/products` | Get subscription plans |
| GET | `/integrations/pks/products/credits` | Get credit packs |
| GET | `/integrations/pks/user-token` | Get payment service token |
| GET | `/integrations/stripe/config` | Get Stripe config |
| GET | `/integrations/stripe/countries` | Get supported countries |
| GET | `/integrations/stripe/sources/user/{userId}` | Get payment methods |

---

## Response Formats

### User Object

```json
{
  "id": 99033,
  "name": "Travis Pezzera",
  "email": "sales@example.com",
  "roles": "user",
  "memoryUsed": 32959163635,
  "memoryLimit": 107374182400,
  "credits": 1700.00,
  "subscriptionTier": {
    "code": "TIER_1",
    "credits": 600,
    "subscribedAt": "2025-07-13T21:53:29.116013Z",
    "creditsUpdatedAt": "2026-03-13T00:00:11.134182Z"
  },
  "address": {...},
  "config": {
    "hideSensitiveData": false,
    "disableNotifications": false
  },
  "extensions": {
    "publications": {"listings": 48, "multiProduct": 12},
    "etsy": {"perDay": 400, "shopCount": 3},
    "shopify": {"perDay": 400, "shopCount": 3},
    "imageMockups": {"listings": 48, "perDay": 9600, "custom": true},
    "removeBackground": {"listings": 120},
    "dreamAi": {"listings": 48},
    ...
  }
}
```

### Subscription Tiers

Based on the extensions data, known tier codes:
- `TIER_1` (Pro) — 600 credits/month, 100GB storage, advanced features
- Higher tiers available with more credits and shop limits

---

## Error Handling

The API returns standard HTTP status codes:

| Status | Meaning |
|---|---|
| 200 | Success |
| 400 | Bad request (missing required parameters) |
| 401 | Unauthorized (session expired or invalid token) |
| 403 | Forbidden (insufficient permissions) |
| 404 | Not found |
| 422 | Validation error |
| 500 | Server error |

Error responses follow the RFC 9110 problem details format:
```json
{
  "type": "https://tools.ietf.org/html/rfc9110#section-15.5.1",
  "title": "Required parameter \"categoryId\" was not provided",
  "status": 400,
  "traceId": "00-a640a049e..."
}
```

---

## Real-Time Events

MyDesigns uses **SignalR** for real-time updates (job completions, notifications, etc.).

```
GET https://api.mydesigns.io/users/hub/negotiate
```

The negotiate endpoint provides connection details for the SignalR hub. The hub broadcasts events such as:
- Job completion (mockup generation, publish status, etc.)
- New notifications
- Credit balance updates

---

## Rate Limits

No official rate limits are documented. The app makes numerous concurrent API calls on each page load (20-30 simultaneous XHR requests). Be considerate with automation.

Per the user extension limits observed:
- Etsy publishing: up to 400 listings per day (Pro plan)
- Shopify publishing: up to 400 listings per day
- Image mockups: up to 9,600 per day
- Remove background: up to 120 per day

---

## Notes on Implementation

1. **CORS**: The API allows requests from `mydesigns.io` origin. When making direct API calls outside a browser, cookies/bearer tokens are needed instead.

2. **Ory CSRF Tokens**: Each login flow has a unique CSRF token that must be passed with form submissions. The token changes between steps.

3. **PKS Products**: The `integrations/pks` endpoints handle payment/subscription flows. The "pks" acronym likely refers to the payment provider (Paddle or similar).

4. **SignalR Hub**: The `/users/hub/negotiate` endpoint is called multiple times on page load (connection establishment). It uses long-polling or WebSocket under the hood.

5. **mydesigns.ai**: There is a separate subdomain `mydesigns.ai` used for AI/tracking features (`mc.mydesigns.ai/t/md-track.js`).

---

## Discovered Subdomains

| Subdomain | Purpose |
|---|---|
| `mydesigns.io` | Main website + SPA frontend |
| `api.mydesigns.io` | Backend REST API |
| `accounts.mydesigns.io` | Ory identity/auth service |
| `community.mydesigns.io` | Community forum (Circle) |
| `t.mydesigns.io` | Internal analytics tracking |
| `mc.mydesigns.ai` | AI features tracking |
| `mydesigns.ai` | AI-related services |

---

## Legal Disclaimer

This client was created by reverse engineering the public-facing web application for legitimate integration and automation purposes. Use responsibly and in accordance with MyDesigns.io's Terms of Service.
