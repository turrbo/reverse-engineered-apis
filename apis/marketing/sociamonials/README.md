# Sociamonials API Client

An unofficial Python client for interacting with the Sociamonials.com social media management platform. This client was created through reverse engineering the web application's API endpoints.

## Overview

Sociamonials is a social media scheduling and management platform. This client provides programmatic access to key features including:

- **Post creation** (publish now, queue, schedule, draft)
- **Post to X/Twitter** with 280-char validation
- **Post to LinkedIn** with image upload support
- **Post to Pinterest** with affiliate link support
- **Image upload** to asset library
- **Media attachments** (images/video)
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

The client requires Python 3.7+ and:

```bash
pip install requests beautifulsoup4
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

### Post Creation

```python
from sociamonials_client import SociamonialAPI

client = SociamonialAPI(
    username="your_username",
    password="your_password"
)
client.login()

# Publish immediately to X/Twitter
result = client.publish_now(
    message="Hello from the API!",
    account_ids=[SociamonialAPI.TWITTER_ACCOUNT_ID]
)
# Returns: {"status": "success", "posts": [{"postid": 123, "network": {"twitter": "1", ...}}]}

# Post to Twitter (convenience method with 280-char validation)
result = client.post_to_twitter(message="My tweet text")

# Schedule a post
result = client.schedule_post(
    message="Scheduled tweet",
    schedule_date="03/25/2026",
    schedule_time="10:00 AM",
    account_ids=[SociamonialAPI.TWITTER_ACCOUNT_ID]
)

# Add to queue
result = client.add_to_queue(message="Queued tweet")

# Save as draft
result = client.save_draft(message="Draft tweet")

# Post with image
result = client.publish_now(
    message="Check this out!",
    account_ids=[SociamonialAPI.TWITTER_ACCOUNT_ID],
    media_path="/path/to/image.png"
)

client.logout()
```

### LinkedIn Posts

```python
from sociamonials_client import SociamonialAPI

client = SociamonialAPI(username="your_username", password="your_password")
client.login()

# Publish immediately to LinkedIn (text only)
result = client.post_to_linkedin(
    message="Excited to share our latest company update with my network!"
)
# Returns: {"status": "success", "posts": [{"postid": 9358170, "network": {"linkedin": "1", ...}}]}

# Publish to LinkedIn with an image (auto-uploads then attaches)
result = client.post_to_linkedin(
    message="Check out this infographic!",
    image_path="/path/to/infographic.jpg"
)

# Schedule a LinkedIn post
result = client.post_to_linkedin(
    message="Join us for our upcoming webinar!",
    schedule_time="2026-04-01T10:00:00"
)

# Manual two-step: upload image first, then post
upload = client.upload_image("/path/to/photo.jpg")
# upload returns: {"id": "...", "name": "...", "loc": "filename.jpg", "width": 1200, "height": 628}
result = client.post_to_linkedin(
    message="Here is our team photo!",
    image_filename=upload["loc"]
)

# Save LinkedIn post as draft
result = client.save_draft(
    message="LinkedIn draft post",
    account_ids=[SociamonialAPI.LINKEDIN_ACCOUNT_ID]
)

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

### Post Creation

#### `publish_now(message, account_ids=None, media_path=None)`
Publish a post immediately via AJAX POST.

**Parameters:**
- `message` (str): Post text
- `account_ids` (list): Account IDs to post to (default: Twitter)
- `media_path` (str): Optional path to image/video file

**Returns:** Dict with `status`, `posts` (array of `{postid, network}`)

**Endpoint:** `POST /accounts/post_to_social_ajax.php`

#### `post_to_twitter(message, schedule_time=None, media_path=None)`
Convenience method for X/Twitter. Validates 280-char limit.

**Parameters:**
- `message` (str): Tweet text (max 280 chars)
- `schedule_time` (str): Optional ISO datetime (e.g., '2026-03-25T10:00:00')
- `media_path` (str): Optional image/video path

#### `post_to_linkedin(message, schedule_time=None, image_path=None, image_filename=None)`
Convenience method for LinkedIn. Validates 3000-char limit. Automatically uploads images.

**Parameters:**
- `message` (str): Post text (max 3000 chars)
- `schedule_time` (str): Optional ISO datetime (e.g., '2026-04-01T10:00:00')
- `image_path` (str): Optional local image path (auto-uploaded via `upload_image()`)
- `image_filename` (str): Optional pre-uploaded image 'loc' value (from `upload_image()`)

**Returns:** Dict with `status`, `posts` (array of `{postid, network}`) for publish now.
Schedule/queue returns `{status, message, redirect_url}`.

#### `upload_image(image_path)`
Upload an image to the Sociamonials asset library. Returns the 'loc' filename for attaching to posts.

**Parameters:**
- `image_path` (str): Local path to image file (JPEG, PNG, GIF, WebP)

**Returns:** Dict with keys `id`, `name`, `loc`, `width`, `height`

**Endpoint:** `POST /accounts/asset_library_image_update.php`

**Example:**
```python
upload = client.upload_image('/path/to/photo.jpg')
print(upload['loc'])  # filename to use as image_filename in post methods
```

#### `add_to_queue(message, account_ids=None, media_path=None, image_filename=None)`
Add a post to the publishing queue (schedule_type=5).

#### `schedule_post(message, schedule_date, schedule_time, account_ids=None, media_path=None, image_filename=None)`
Schedule a post for a specific date/time (schedule_type=2).

**Parameters:**
- `schedule_date` (str): Date (e.g., '03/25/2026')
- `schedule_time` (str): Time (e.g., '10:00 AM')
- `image_filename` (str): Optional pre-uploaded image 'loc' value from `upload_image()`

#### `save_draft(message, account_ids=None, media_path=None, image_filename=None)`
Save a post as draft (schedule_type=1, publish_status=0).

#### Account IDs
```python
SociamonialAPI.TWITTER_ACCOUNT_ID    = '17019'
SociamonialAPI.LINKEDIN_ACCOUNT_ID   = '14029_0_0'   # for select_accounts[]
SociamonialAPI.LINKEDIN_SELECTED_IDS = '14029|0|0'   # pipe-separated for ln_selected_ids
SociamonialAPI.PINTEREST_ACCOUNT_ID  = '9313'
```

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
- `POST /accounts/post_to_social_ajax.php` - **All post creation** (publish/queue/schedule/draft, AJAX, returns JSON)
- `POST /accounts/asset_library_image_update.php` - **Upload image** to asset library (returns {id, name, loc, width, height})
- `POST /accounts/grid_data.php` - DataTables endpoint for posts (queue, sent, drafts)
- `POST /accounts/get_heartbit.php` - Session heartbeat/extension
- `POST /accounts/ajax_common.php` - Common AJAX operations
- `POST /accounts/grid_updatedata.php` - Update post data
- `POST /accounts/grid_deletedata.php` - Delete post data
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

### Publish Now Response (sm_ajax_publish_type=1)
```json
[{
  "postid": 9358170,
  "network": {
    "facebook": "0",
    "twitter": "0",
    "linkedin": "1",
    "instagram": "0",
    "bluesky": "0",
    "threads": "0",
    "gmb": "0",
    "pinterest": "0",
    "tiktok": "0",
    "youtube": "0"
  }
}]
```

### Queue/Schedule/Draft Response (sm_ajax_publish_type=2,3,4,5)
```json
[{
  "refid": "12345",
  "msg": "2"
}]
```

Response `msg` codes:
- `"1"`: Verification report / duplicate check triggered
- `"2"`: Successfully queued or scheduled
- `"8"`: Draft saved successfully

### Image Upload Response (asset_library_image_update.php)
```json
{
  "id": "98765",
  "name": "photo.jpg",
  "loc": "2026/03/25/photo_1743000000.jpg",
  "width": "1200",
  "height": "628"
}
```

The `loc` field is the filename to pass as `image_filename` to post creation methods.

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
- ✅ **Create new posts** (publish now, queue, schedule, draft)
- ✅ **Schedule posts** (specific date/time)
- ✅ **Queue posts** (add to publishing queue)
- ✅ **Save drafts**
- ✅ **Upload images** to asset library (`upload_image()`)
- ✅ **Post to X/Twitter** (with 280-char validation)
- ✅ **Post to LinkedIn** (with image upload support, 3000-char validation)
- ✅ **Post to Pinterest** (with affiliate link and board selection)
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
- ❌ Update existing posts
- ❌ Delete posts
- ❌ Manage campaigns
- ❌ Parse HTML responses from page endpoints

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

### Post Creation via Dashboard Form Parsing

The post creation endpoint (`post_to_social_ajax.php`) requires ALL 230+ fields from the dashboard's `#f1` form (submitted via `$('#f1').serialize()`). Sending only the essential fields results in an empty response.

The client handles this by:
1. Loading the dashboard page (`/accounts/social_media.php`)
2. Parsing all default form field values using BeautifulSoup
3. Overriding only the fields we need (message, accounts, schedule_type, etc.)
4. Serializing the full form data for submission

**All 5 post creation flows use `post_to_social_ajax.php`** with `sm_ajax_publish_type` controlling the action:
- `sm_ajax_publish_type=1` → Publish Now → returns `[{postid, network}]`
- `sm_ajax_publish_type=2` → Add to Queue → returns `[{refid, msg}]` (msg='2' = success)
- `sm_ajax_publish_type=3` → Schedule → returns `[{refid, msg}]` (msg='2' = success)
- `sm_ajax_publish_type=4` → Optimal Time → returns `[{refid, msg}]`
- `sm_ajax_publish_type=5` → Save Draft → returns `[{refid, msg}]` (msg='8' = draft saved)

**Key form fields:**
- `message`: Post text
- `select_accounts[]`: Checkbox values for platform selection
- `tw_selected_ids`: Twitter account ID(s) comma-separated
- `ln_selected_ids`: LinkedIn account ID in pipe-separated format (e.g. `14029|0|0`)
- `pi_selected_ids`: Pinterest account ID(s)
- `schedule_type`: 1=publish, 2=schedule, 4=optimal, 5=queue
- `publish_status`: 1=publish now, 0=queue/draft/schedule
- `publish_socialmedia`: 'add' (action indicator)
- `edit_ln_message`: Per-platform message override for LinkedIn
- `asset_image_social_network[]`: Media file upload (multipart)

**LinkedIn image attachment fields** (after uploading via `asset_library_image_update.php`):
- `social_add_from_library_val`: The uploaded image filename ('loc' from upload response)
- `attach_video_type`: '4' (indicates image attachment)
- `sm_ln_attach_media`: '1' (enables LinkedIn media)

**LinkedIn account ID format:**
- `select_accounts[]` uses underscore format: `14029_0_0`
- `ln_selected_ids` uses pipe-separated format: `14029|0|0`

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
4. Post creation requires loading the full dashboard page (230+ form fields) on first call to build defaults
5. Account IDs are hardcoded from discovery - may differ per Sociamonials account
6. No official API documentation exists
7. LinkedIn image attachment requires a two-step process: upload first via `upload_image()`, then reference the `loc` filename when creating the post

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
