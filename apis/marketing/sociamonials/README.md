# Sociamonials API Client

An unofficial Python client for interacting with the Sociamonials.com social media management platform. This client was created through reverse engineering the web application's API endpoints.

## Overview

Sociamonials is a social media scheduling and management platform. This client provides programmatic access to key features including:

- Social media post management (queue, sent, drafts)
- Calendar view
- Reports and analytics
- Campaigns/Social Tiles
- Social CRM database
- AI Writer
- Account settings and integrations

## Authentication

The API uses session-based authentication via cookies. The client handles login automatically using username and password credentials.

### Authentication Flow

1. POST credentials to `login.php`
2. Response from `password.php` returns JSON with session info:
   - `user_id`: User identifier
   - `user_hash`: User hash token
   - `login_status`: Login success indicator
3. Session maintained via `PHPSESSID` cookie
4. Additional session cookies: `sociamonials-usr` and `sociamonials-rem-usr` (base64 encoded)

## Installation

The client requires Python 3.7+ and the `requests` library:

```bash
pip install requests
```

## Usage

### Basic Example

```python
from sociamonials_client import SociamonialAPI

# Initialize client with credentials
client = SociamonialAPI(
    username="your_username",
    password="your_password"
)

# Login
client.login()

# Get queued posts
queued_posts = client.get_queued_posts(length=10)
print(f"Total queued: {queued_posts['recordsTotal']}")

# Get sent posts
sent_posts = client.get_sent_posts(length=10)
print(f"Total sent: {sent_posts['recordsTotal']}")

# Logout
client.logout()
```

### Using Environment Variables

For security, credentials should be provided via environment variables:

```bash
export SOCIAMONIALS_USERNAME="your_username"
export SOCIAMONIALS_PASSWORD="your_password"
python sociamonials_client.py
```

## API Endpoints

### Authentication

#### `login()`
Authenticate with Sociamonials.

**Returns:** Dict with login response including `user_id`, `user_hash`, `login_status`

**Example:**
```python
result = client.login()
print(f"User ID: {result['user_id']}")
```

#### `logout()`
End the current session.

**Returns:** `True` if successful

---

### Session Management

#### `extend_session()`
Extend/refresh the current session (heartbeat).

**Returns:** Dict with session status

**Example:**
```python
status = client.extend_session()
print(f"Session expired: {status[0]['is_expired']}")
```

---

### Post Management

#### `get_posts(page_name, status, search_type, start, length, search_value)`
Generic method to retrieve posts with DataTables pagination.

**Parameters:**
- `page_name` (str): Type of posts ('pending_posts', 'published_posts', 'draft_posts')
- `status` (int): Status code (1=sent, 2=draft, 3=queued)
- `search_type` (str): Search type ('message', 'date', etc.)
- `start` (int): Pagination offset (default: 0)
- `length` (int): Number of records (default: 10)
- `search_value` (str): Search query (default: '')

**Returns:** DataTables JSON response with posts data

**Endpoint:** `POST /accounts/grid_data.php`

#### `get_queued_posts(start=0, length=10)`
Get posts in the queue (scheduled/pending).

**Example:**
```python
posts = client.get_queued_posts(length=20)
for post_data in posts['data']:
    print(post_data)
```

#### `get_sent_posts(start=0, length=10)`
Get published/sent posts.

#### `get_draft_posts(start=0, length=10)`
Get draft posts.

---

### Content & Features

#### `get_calendar_data()`
Get calendar view HTML/data.

**Returns:** String (HTML content)

**Endpoint:** `GET /accounts/calendar.php`

#### `get_reports()`
Get social media reports and analytics.

**Returns:** String (HTML content)

**Endpoint:** `GET /accounts/socialmedia_report.php`

#### `get_campaigns()`
Get campaigns/social tiles management page.

**Returns:** String (HTML content)

**Endpoint:** `GET /accounts/manage_socialtiles.php`

#### `get_social_crm()`
Get Social CRM database.

**Returns:** String (HTML content)

**Endpoint:** `GET /accounts/socialcrm_database.php`

#### `get_ai_writer()`
Get AI Writer page.

**Returns:** String (HTML content)

**Endpoint:** `GET /accounts/ai_writer.php`

---

### Account Management

#### `get_account_settings()`
Get account settings page.

**Returns:** String (HTML content)

**Endpoint:** `GET /accounts/account_settings.php`

#### `get_integrations()`
Get account integrations page.

**Returns:** String (HTML content)

**Endpoint:** `GET /accounts/account_integrations.php`

---

## Discovered Endpoints

### Base URL
```
https://www.sociamonials.com
```

### Authentication Endpoints
- `POST /login.php` - Login page
- `POST /password.php` - Authentication handler (returns JSON)
- `GET /logout.php` - Logout

### Account Pages
- `GET /accounts/social_media.php` - Main dashboard
- `GET /accounts/calendar.php` - Calendar view
- `GET /accounts/socialmedia_report.php` - Reports/Analytics
- `GET /accounts/manage_socialtiles.php` - Campaigns/Social Tiles
- `GET /accounts/ai_writer.php` - AI Writer
- `GET /accounts/employee_posts.php` - Approve posts
- `GET /accounts/manage_sharebuttons.php` - Share buttons
- `GET /accounts/socialcrm_database.php` - Social CRM
- `GET /accounts/account_settings.php` - Account settings
- `GET /accounts/account_preferences.php` - Account preferences
- `GET /accounts/account_integrations.php` - Integrations
- `GET /accounts/manage_users.php` - User management
- `GET /accounts/tutorials.php` - Tutorial videos
- `GET /accounts/agency_dashboard.php` - Agency dashboard
- `GET /accounts/customer_photos.php` - Customer photos

### AJAX/API Endpoints
- `POST /accounts/grid_data.php` - DataTables endpoint for posts (queue, sent, drafts)
- `POST /accounts/get_heartbit.php` - Session heartbeat/extension
- `POST /accounts/ajax_common.php` - Common AJAX operations
- `POST /accounts/grid_updatedata.php` - Update post data
- `POST /accounts/grid_deletedata.php` - Delete post data
- `POST /accounts/asset_library_image_update.php` - Update asset library images
- `GET /accounts/display_customer_video.php` - Display customer video
- `GET /accounts/change_link.php` - Change link
- `GET /accounts/social_media_display_photo.php` - Display photo

### Query Parameters for grid_data.php

The `grid_data.php` endpoint uses these parameters:

**URL Parameters:**
- `pageName`: Type of posts (e.g., `pending_posts`, `published_posts`, `draft_posts`)
- `status`: Status code (1=sent, 2=draft, 3=queued)
- `search_type`: Search field type (e.g., `message`, `date`)
- `sm_timeformat_id`: Time format ID (typically `1`)

**POST Data (DataTables format):**
- `draw`: DataTables draw counter
- `start`: Pagination offset
- `length`: Number of records per page
- `search[value]`: Search query string
- `columns[i][data]`: Column data index
- `order[0][column]`: Sort column
- `order[0][dir]`: Sort direction (asc/desc)

## Response Formats

### Login Response
```json
{
  "pagename": "accounts/social_media.php",
  "res_status": "success",
  "login_status": "1",
  "user_id": "sm35944dsly",
  "user_hash": "c209e5b665229a3da28ec388792b976dcc2aeb4b3cb076d1ba041c28fd90"
}
```

### Session Heartbeat Response
```json
[{
  "is_expired": "0",
  "remaining_time_warn": "0",
  "logout_time_flag": "0",
  "lgout_time_cnter": "5400",
  "wtm_post_ids": ""
}]
```

### Posts Response (DataTables)
```json
{
  "draw": 1,
  "recordsTotal": 0,
  "recordsFiltered": 0,
  "data": []
}
```

## Features

### Supported Operations
- ✅ Authentication (login/logout)
- ✅ Session management (heartbeat)
- ✅ Retrieve queued posts
- ✅ Retrieve sent posts
- ✅ Retrieve draft posts
- ✅ Access calendar data
- ✅ Access reports/analytics
- ✅ Access campaigns
- ✅ Access Social CRM
- ✅ Access AI Writer
- ✅ Access account settings
- ✅ Access integrations

### Not Yet Implemented
- ❌ Create new posts
- ❌ Update existing posts
- ❌ Delete posts
- ❌ Upload media/assets
- ❌ Schedule posts
- ❌ Manage campaigns
- ❌ Parse HTML responses from page endpoints

These features require additional reverse engineering to discover the exact API endpoints and payload formats.

## Technical Details

### Cookie-Based Authentication
The platform uses PHP sessions with the following cookies:
- `PHPSESSID`: Main session identifier
- `sociamonials-usr`: User identification (base64 encoded)
- `sociamonials-rem-usr`: "Remember me" user data (base64 encoded)

### Request Headers
The client uses these headers to mimic browser behavior:
```python
{
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Accept': 'application/json, text/javascript, */*; q=0.01',
    'Accept-Language': 'en-US,en;q=0.9',
    'X-Requested-With': 'XMLHttpRequest',
    'Referer': 'https://www.sociamonials.com/accounts/social_media.php'
}
```

### DataTables Integration
Many endpoints use the DataTables server-side processing format. The client automatically formats requests with proper pagination, sorting, and filtering parameters.

## Error Handling

The client includes error handling for:
- Authentication failures
- Network errors
- Invalid JSON responses
- Session expiration
- Empty responses from endpoints

## Security Notes

- **Never hardcode credentials** in your scripts
- Use environment variables for username/password
- The client does not store credentials on disk
- Session cookies are maintained in memory only
- Always call `logout()` when finished

## Limitations

This is an **unofficial** reverse-engineered client. Be aware:

1. The API is undocumented and may change without notice
2. Rate limiting is unknown - use responsibly
3. Some endpoints return HTML instead of JSON (calendar, reports, etc.)
4. Not all features are implemented (creating posts, file uploads, etc.)
5. No official API documentation exists

## Example Output

```
Initializing Sociamonials API client...

1. Authenticating...
✓ Login successful! User ID: sm35944dsly
   User ID: sm35944dsly

2. Extending session (heartbeat)...
   Heartbeat response: [{'is_expired': '0', 'remaining_time_warn': '0', ...}]

3. Fetching queued posts...
   Total queued posts: 0
   Fetched: 0 posts

4. Fetching sent posts...
   Total sent posts: 0
   Fetched: 0 posts

5. Fetching draft posts...
   Total draft posts: 0
   Fetched: 0 posts

6. Fetching calendar data...
   Calendar page size: 647816 bytes

7. Fetching reports...
   Reports page size: 139145 bytes

✅ All API calls successful!

8. Logging out...
✓ Logged out successfully
```

## Contributing

Since this is a reverse-engineered client, contributions to discover and implement additional endpoints are welcome. To add new features:

1. Use browser developer tools to capture API requests
2. Identify the endpoint, method, parameters, and response format
3. Implement the method in the `SociamonialAPI` class
4. Add documentation to this README

## License

This client is provided as-is for educational and research purposes. Use responsibly and in accordance with Sociamonials' terms of service.

## Disclaimer

This is an **unofficial** client created through reverse engineering. It is not affiliated with, endorsed by, or supported by Sociamonials. Use at your own risk.
