# VinWiki API Client

A fully functional Python client for the VinWiki REST API (https://rest.vinwiki.com), a vehicle history and car enthusiast social platform.

## Overview

VinWiki (web.vinwiki.com) is a platform where users can:
- Look up vehicle information by VIN
- View vehicle post feeds and histories
- Track vehicle ownership and modifications
- Search for vehicles by make, model, or VIN
- Follow vehicles and users
- Browse user feeds and profiles

This Python client provides a convenient interface to interact with VinWiki's API programmatically.

## Important Security Notes

- **Never hardcode credentials** in your Python scripts
- **Always use environment variables** for authentication
- **Do not commit credentials** to version control
- **Keep your credentials secure** and private

## Installation

### Requirements

- Python 3.7+
- `requests` library

### Install Dependencies

```bash
pip install requests
```

## Quick Start

### Option 1: Using Email/Password (Recommended)

```bash
export VINWIKI_EMAIL="your@email.com"
export VINWIKI_PASSWORD="your_password"
python vinwiki_client.py
```

### Option 2: Using Token Directly

```bash
export VINWIKI_TOKEN="your_session_token"
python vinwiki_client.py
```

### Basic Usage

```python
from vinwiki_client import VinWikiClient
import os

# Initialize with credentials
client = VinWikiClient(
    email=os.getenv('VINWIKI_EMAIL'),
    password=os.getenv('VINWIKI_PASSWORD')
)

# Login (or use set_token if you have a token)
client.login()

# Or use an existing token
# client.set_token("your_token_here")

# Get notification count
notifications = client.get_notification_count()
print(f"Unseen: {notifications['notification_count']['unseen']}")

# Search for vehicles
results = client.search_vehicles("Ford GT")
for vehicle in results['results']['vehicles'][:5]:
    print(f"{vehicle['long_name']} - VIN: {vehicle['vin']}")

# Get vehicle details by VIN
vehicle_info = client.get_vehicle_by_vin("1FAFP90S56Y401183")
vehicle = vehicle_info['vehicle']
print(f"{vehicle['year']} {vehicle['make']} {vehicle['model']}")
print(f"Followers: {vehicle['follower_count']}, Posts: {vehicle['post_count']}")

# Get vehicle post feed
feed = client.get_vehicle_feed("1FAFP90S56Y401183")
for post in feed['feed'][:5]:
    p = post['post']
    print(f"[{p['post_date_ago']}] {p['post_text']}")

# Get recent VINs
recent = client.get_recent_vins()
for vehicle in recent['recent_vins'][:5]:
    print(f"{vehicle['long_name']} - VIN: {vehicle['vin']}")
```

## API Endpoints

All endpoints use the base URL: `https://rest.vinwiki.com`

Authentication is done via the `Authorization` header with the session token.

### Discovered Endpoints

#### Authentication
- `POST /auth/authenticate` - Login with email/password
  - Request: `{"login": "email@example.com", "password": "password"}`
  - Returns: Session cookie (vw_ci_session)
  - Note: Token is stored in localStorage as `vwSessionToken` in the browser

#### User/Person Endpoints
- `GET /person/notification_count/me` - Get notification count for current user
- `GET /person/feed/{user_uuid}` - Get user's feed
- `GET /person/recent_vins` - Get recently viewed VINs
- `GET /person/profile/{user_uuid}` - Get user profile
- `GET /person/profile_picture/{user_uuid}` - Get user's profile picture

#### Vehicle Endpoints
- `GET /vehicle/vin/{vin}` - Get vehicle information by VIN
- `GET /vehicle/feed/{vin}` - Get post feed for a vehicle
- `GET /vehicle/is_following/{vin}` - Check if user is following a vehicle
- `GET /vehicle/search?q={query}` - Search for vehicles
- `POST /vehicle/follow/{vin}` - Follow a vehicle (requires auth)
- `POST /vehicle/unfollow/{vin}` - Unfollow a vehicle (requires auth)

## API Methods

### Authentication

#### `login()`
Authenticate with VinWiki using email and password.

```python
client.login()
```

**Note:** Currently returns session cookie authentication. The token can be extracted from localStorage in browser as `vwSessionToken`.

#### `set_token(token, user_uuid=None)`
Manually set authentication token if you already have one.

```python
client.set_token("your_token_here", "user_uuid_optional")
```

### User Operations

#### `get_notification_count()`
Get current user's notification count.

```python
notifications = client.get_notification_count()
print(notifications['notification_count']['unseen'])
```

**Response:**
```json
{
  "notification_count": {
    "unseen": 0
  },
  "status": "ok"
}
```

#### `get_user_feed(user_uuid)`
Get feed for a specific user.

```python
feed = client.get_user_feed("user-uuid-here")
```

#### `get_recent_vins()`
Get recently viewed VINs.

```python
recent = client.get_recent_vins()
for vehicle in recent['recent_vins']:
    print(vehicle['long_name'], vehicle['vin'])
```

**Response:**
```json
{
  "recent_vins": [
    {
      "make": "Ford",
      "model": "GT",
      "year": "2006",
      "vin": "1FAFP90S56Y401183",
      "long_name": "2006 Ford GT",
      "poster_photo": "https://media-cdn.vinwiki.com/...",
      "icon_photo": "https://media-cdn.vinwiki.com/..."
    }
  ]
}
```

#### `get_user_profile(user_uuid)`
Get user profile information.

```python
profile = client.get_user_profile("user-uuid")
print(profile['profile']['username'])
```

**Response:**
```json
{
  "profile": {
    "uuid": "...",
    "username": "username",
    "first_name": null,
    "last_name": null,
    "following_vehicle_count": 0,
    "follower_count": 2,
    "following_count": 0,
    "post_count": 43,
    "avatar": "...",
    "location": "Florida",
    "bio": ""
  },
  "status": "ok"
}
```

### Vehicle Operations

#### `get_vehicle_by_vin(vin)`
Get vehicle information by VIN.

```python
vehicle_info = client.get_vehicle_by_vin("1FAFP90S56Y401183")
vehicle = vehicle_info['vehicle']
```

**Response:**
```json
{
  "vehicle": {
    "make": "Ford",
    "model": "GT",
    "year": "2006",
    "trim": "",
    "long_name": "2006 Ford GT",
    "vin": "1FAFP90S56Y401183",
    "poster_photo": "https://...",
    "icon_photo": "https://...",
    "id": 1003234,
    "follower_count": 2,
    "post_count": 4,
    "decoder_fail": false,
    "user_updated": true,
    "ownership": true
  },
  "status": "ok"
}
```

#### `get_vehicle_feed(vin)`
Get post feed for a vehicle.

```python
feed = client.get_vehicle_feed("1FAFP90S56Y401183")
for post in feed['feed']:
    p = post['post']
    print(f"[{p['post_date_ago']}] {p['post_text']}")
```

**Response:**
```json
{
  "feed": [
    {
      "post": {
        "uuid": "...",
        "id": 7739822,
        "type": "list_add",
        "post_text": "Added to list '2006 Ford GT'",
        "comment_count": 0,
        "post_date": "2024-07-17T23:31:38+00:00",
        "post_date_ago": "2 years ago",
        "person": {
          "username": "F0RDGT",
          "avatar": "..."
        },
        "vehicle": {
          "vin": "1FAFP90S56Y401183",
          "long_name": "2006 Ford GT"
        },
        "image": {}
      }
    }
  ]
}
```

#### `search_vehicles(query)`
Search for vehicles.

```python
results = client.search_vehicles("Ford Mustang")
for vehicle in results['results']['vehicles']:
    print(vehicle['long_name'])
```

**Response:**
```json
{
  "results": {
    "vehicles": [
      {
        "vin": "...",
        "make": "Ford",
        "model": "Mustang",
        "year": "2016",
        "long_name": "2016 Ford Mustang",
        "icon_photo": "..."
      }
    ]
  }
}
```

#### `is_following_vehicle(vin)`
Check if following a vehicle.

```python
status = client.is_following_vehicle("1FAFP90S56Y401183")
```

#### `follow_vehicle(vin)` / `unfollow_vehicle(vin)`
Follow or unfollow a vehicle.

```python
client.follow_vehicle("1FAFP90S56Y401183")
client.unfollow_vehicle("1FAFP90S56Y401183")
```

## Running the Test Script

```bash
# With email/password
export VINWIKI_EMAIL="your@email.com"
export VINWIKI_PASSWORD="your_password"
python vinwiki_client.py

# Or with token
export VINWIKI_TOKEN="your_token"
python vinwiki_client.py
```

## Getting Your Session Token

If you want to use a token directly instead of logging in:

1. Log in to https://web.vinwiki.com in your browser
2. Open Developer Tools (F12)
3. Go to Application > Local Storage > https://web.vinwiki.com
4. Find the key `vwSessionToken` - this is your token
5. Use it with `client.set_token("your_token_here")`

## Example: Complete Vehicle Lookup

```python
import os
from vinwiki_client import VinWikiClient

# Initialize
client = VinWikiClient(
    email=os.getenv('VINWIKI_EMAIL'),
    password=os.getenv('VINWIKI_PASSWORD')
)

# Login
client.login()

# Search for a vehicle
vin = "1FAFP90S56Y401183"

# Get vehicle details
vehicle_info = client.get_vehicle_by_vin(vin)
vehicle = vehicle_info['vehicle']

print(f"Vehicle: {vehicle['long_name']}")
print(f"VIN: {vehicle['vin']}")
print(f"Followers: {vehicle['follower_count']}")
print(f"Posts: {vehicle['post_count']}")

# Get vehicle feed/history
feed = client.get_vehicle_feed(vin)
print(f"\nVehicle History ({len(feed['feed'])} posts):")
for post in feed['feed']:
    p = post['post']
    person = p['person']['username']
    print(f"  [{p['post_date_ago']}] {person}: {p['post_text']}")

# Check if following
following = client.is_following_vehicle(vin)
print(f"\nFollowing this vehicle: {following}")
```

## Error Handling

```python
import requests
from vinwiki_client import VinWikiClient

client = VinWikiClient(email="...", password="...")

try:
    client.login()
    vehicle = client.get_vehicle_by_vin("INVALID_VIN")
except requests.HTTPError as e:
    print(f"HTTP Error: {e}")
    print(f"Response: {e.response.text}")
except Exception as e:
    print(f"Error: {e}")
```

## Rate Limiting

Be respectful of VinWiki's servers:
- Add delays between requests if making many calls
- Don't hammer the API with rapid requests
- Cache results when possible

```python
import time

for vin in vin_list:
    vehicle = client.get_vehicle_by_vin(vin)
    # Process vehicle...
    time.sleep(1)  # Be nice to the API
```

## Reverse Engineering Notes

This client was created by reverse engineering the VinWiki web application:

1. **Network Capture**: Used browser DevTools to monitor API calls
2. **Authentication Flow**: Discovered POST to /auth/authenticate with login/password
3. **Token Extraction**: Found token stored in localStorage as `vwSessionToken`
4. **Authorization**: Confirmed token is sent via `Authorization` header
5. **Endpoint Discovery**: Mapped out person, vehicle, and feed endpoints
6. **Response Analysis**: Documented JSON response structures

### Key Findings

- Base API URL: `https://rest.vinwiki.com`
- Authentication: Token-based via Authorization header
- User identifier: UUID (not numeric ID)
- Vehicle identifier: VIN (17-character)
- All responses include `"status": "ok"` on success

## Troubleshooting

### Login Issues

If login doesn't work with email/password, try using a token directly:
1. Log in manually at web.vinwiki.com
2. Extract token from localStorage
3. Use `client.set_token(token)`

### API Changes

If endpoints change:
1. Check browser DevTools Network tab
2. Find the new endpoint URL
3. Update the client code
4. Test and verify

## Disclaimer

This is an unofficial client created through reverse engineering for educational purposes.

- Use responsibly and respect VinWiki's Terms of Service
- Do not abuse the API or make excessive requests
- Keep your credentials secure
- This client is not affiliated with or endorsed by VinWiki

## License

This is educational/research code. Use at your own risk.

VinWiki and its API are owned by VinWiki LLC.
