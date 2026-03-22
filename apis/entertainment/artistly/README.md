# Artistly.ai API Documentation

**Reverse Engineered API Documentation for app.artistly.ai**

Date: 2026-03-22
Platform: Laravel + Inertia.js
Authentication: Session-based with CSRF tokens

---

## Overview

Artistly.ai is an AI image generation platform that uses a Laravel backend with Inertia.js for server-side rendering. The API uses session-based authentication with CSRF token protection.

## Authentication

### Method: Email/Password Login with Session Cookies

**Endpoint:** `POST /login`

**Authentication Flow:**

1. **Get CSRF Token**
   - `GET https://app.artistly.ai/login`
   - Extract `XSRF-TOKEN` cookie from response
   - URL-decode the token value

2. **Submit Login**
   - `POST https://app.artistly.ai/login`
   - Headers:
     ```
     Content-Type: application/x-www-form-urlencoded
     X-XSRF-TOKEN: {decoded_xsrf_token}
     Origin: https://app.artistly.ai
     Referer: https://app.artistly.ai/login
     ```
   - Body:
     ```
     email={email}
     password={password}
     remember=false
     ```
   - Expected Response: `302` redirect to `/dashboard`

3. **Session Persistence**
   - After successful login, the following cookies are set:
     - `XSRF-TOKEN` - CSRF protection token (must be URL-decoded and sent in `X-XSRF-TOKEN` header)
     - `artistly_session` - Main session identifier
     - `CSRF` - Additional CSRF token
     - `remember_web_*` - Remember-me token (optional)

### Making Authenticated Requests

For all authenticated API requests:

**Required Headers:**
```
X-XSRF-TOKEN: {url_decoded_xsrf_token}
X-Requested-With: XMLHttpRequest
Origin: https://app.artistly.ai
Referer: https://app.artistly.ai/{relevant-page}
```

**Cookies:**
- Include all session cookies from login response

## API Endpoints

### Image Generation

#### 1. T-Shirt Design Generation

**Endpoint:** `POST /tshirt-images`

**Purpose:** Generate T-shirt design images with specified prompts and styles

**Headers:**
```
Content-Type: application/json
X-XSRF-TOKEN: {token}
X-Requested-With: XMLHttpRequest
Origin: https://app.artistly.ai
Referer: https://app.artistly.ai/choose-designer
```

**Request Body:**
```json
{
  "tshirt_prompts": ["prompt1", "prompt2", ...],
  "style": "36"
}
```

**Parameters:**
- `tshirt_prompts` (array, required): List of text prompts for image generation
- `style` (string, required): Style ID from available illustrator styles

**Response:**
- Status: `200 OK`
- Type: Inertia.js HTML response with embedded JSON
- Behavior: Initiates asynchronous image generation and redirects to personal designs page
- Images appear in user's personal gallery when generation completes

**Example:**
```python
{
  "tshirt_prompts": ["A cute cat wearing sunglasses", "A dragon breathing fire"],
  "style": "36"  # 2D Flat style
}
```

**Status:** ✅ **WORKING**

---

#### 2. Storybook Illustration Generation

**Endpoint:** `POST /story-book-images`

**Purpose:** Generate storybook-style illustrations

**Request Body:**
```json
{
  "prompts": ["prompt1", "prompt2", ...],
  "style": "style_id"
}
```

**Parameters:**
- `prompts` (array, required): List of text prompts
- `style` (string, optional): Style ID for illustrations

**Status:** ✅ **AVAILABLE** (same pattern as tshirt-images)

---

#### 3. Image Stylization

**Endpoint:** `POST /stylize-image`

**Purpose:** Apply AI style transfer to an existing image

**Request Body:**
```json
{
  "image_url": "https://...",
  "style": "style_id",
  "prompt": "optional text prompt"
}
```

**Status:** ✅ **AVAILABLE**

---

#### 4. AI Agent Generation (Generic)

**Endpoint:** `POST /ai-agent`

**Purpose:** Generic AI agent interface for various generation tasks

**Request Body:**
```json
{
  "agent": "agent_class_name",
  "prompt": "text prompt",
  "...": "additional parameters"
}
```

**Note:** Requires specific agent class names that are registered in the backend. Common agent classes were not discovered during reconnaissance.

**Status:** ⚠️ **PARTIALLY WORKING** (requires correct agent class name)

---

### Design Management

#### 5. Get Personal Designs

**Endpoint:** `GET /fetch-personal-designs`

**Purpose:** Retrieve user's generated images

**Parameters:** Query parameters for pagination (not fully documented)

**Response:**
```json
{
  "designs": [...],
  "hasMore": boolean,
  "folders": [...]
}
```

**Status:** ✅ **WORKING**

---

#### 6. Download Design

**Endpoint:** `GET /{uuid}/download`

**Purpose:** Download a generated image by UUID

**URL Parameters:**
- `uuid` (string, required): Design UUID

**Response:** Binary image data

**Status:** ✅ **WORKING**

---

#### 7. Create Folder

**Endpoint:** `POST /designs/folder`

**Purpose:** Create a new design folder

**Request Body:**
```json
{
  "name": "folder_name"
}
```

**Status:** ✅ **AVAILABLE**

---

#### 8. Delete Designs

**Endpoint:** `POST /delete-designs`

**Purpose:** Delete one or more designs

**Request Body:**
```json
{
  "design_ids": [...]
}
```

**Status:** ✅ **AVAILABLE**

---

### User Information

#### 9. Dashboard Data

**Endpoint:** `GET /dashboard`

**Purpose:** Get user account info, folders, settings, and available features

**Response:** HTML page with Inertia.js data embedded in `data-page` attribute

**Extracting Data:**
```python
import re
import html
import json

response = session.get("https://app.artistly.ai/dashboard")
pattern = r'<div id="app" data-page="([^"]+)"'
match = re.search(pattern, response.text)
if match:
    page_data = html.unescape(match.group(1))
    data = json.loads(page_data)

    user = data['props']['auth']['user']
    folders = data['props']['personal_folders']
    styles = data['props']['illustratorStyles']
```

**Available Data:**
- `props.auth.user`: User information
  - `id`, `name`, `email`, `role`, `status`
  - `products`: Subscribed products
  - `features`: Enabled features
- `props.folders`: Available folders
- `props.illustratorStyles`: Available art styles
- `props.concurrent_generation_count`: Current running generations
- `props.concurrent_generation_limit`: Max concurrent generations

**Status:** ✅ **WORKING**

---

### Illustrator Styles

The platform supports 81+ different illustration styles. Each style has:

**Style Object:**
```json
{
  "label": "2d Flat",
  "style": "36",
  "cover": "https://cdn.artistly.ai/...",
  "prefix": "Kurzgesagt style",
  "suffix": null,
  "description": null
}
```

**Common Styles:**
- `36` - 2D Flat (Kurzgesagt style)
- `8bitpixelv5` - 8-bit Pixel Style
- `131` - AAA Game Style
- `adltclr` - Adult Coloring Book
- `anime` - Anime Style
- `cartoon` - Cartoon Style

**Getting All Styles:**
Access the dashboard and extract from `props.illustratorStyles`

---

### Other Available Endpoints

The following endpoints were discovered but not fully tested:

#### Generation Tools
- `POST /ai-image-designer` - AI Image Designer
- `POST /generate-seamless-pattern` - Seamless pattern generation
- `POST /generate-wall-art-sketch` - Wall art sketch generation
- `POST /photo-editor/edit` - Photo editing
- `POST /flipbook-generate-template` - Flipbook generation

#### Design Operations
- `POST /change-folder` - Move design to different folder
- `POST /design-tags/add` - Add tags to design
- `DELETE /design-tags/remove` - Remove tags from design
- `GET /design-tags/{uuid}` - Get tags for a design
- `POST /create-zip` - Create zip archive of designs
- `GET /download-zip` - Download zip archive

#### Other Features
- `GET /ai-text-to-image` - Text to image page
- `GET /ai-outpainter` - Image outpainting tool
- `GET /ai-inpainter` - Image inpainting tool
- `GET /logo-maker` - Logo maker tool
- `GET /mockup-creator` - Mockup creator

---

## Rate Limits

- **Concurrent Generations:** Users have a concurrent generation limit (e.g., 65)
- **Daily Limits:** Varies by subscription plan
- **No explicit rate limiting observed** during testing

---

## Error Handling

### Common HTTP Status Codes

- `200 OK` - Request successful (may return HTML for Inertia.js)
- `302 Found` - Redirect (common after successful operations)
- `401 Unauthorized` - Not authenticated or session expired
- `419 Page Expired` - CSRF token missing or invalid
- `422 Unprocessable Entity` - Validation error

### Error Response Format

```json
{
  "message": "The agent field is required.",
  "errors": {
    "field_name": [
      "Error message 1",
      "Error message 2"
    ]
  }
}
```

---

## Important Notes

### Asynchronous Generation

Image generation is **asynchronous**:
1. POST request to generation endpoint returns immediately
2. Response is a redirect to personal designs page
3. Images appear in personal gallery when generation completes
4. Poll `/fetch-personal-designs` to check for new images

### CSRF Token Handling

- **URL Decoding:** The `XSRF-TOKEN` cookie is URL-encoded and must be decoded before use
- **Token Refresh:** XSRF token is refreshed with each request; always use latest value from cookies
- **Header Requirement:** Must send decoded token in `X-XSRF-TOKEN` header

### Session Management

- Sessions expire after inactivity (timeout period not documented)
- Re-login required after session expiration
- Remember-me token extends session lifetime

---

## Python Client Usage

```python
import os
from artistly_client import ArtistlyClient

# Set credentials via environment variables (NEVER hardcode!)
email = os.getenv("ARTISTLY_EMAIL")
password = os.getenv("ARTISTLY_PASSWORD")

# Initialize and login
client = ArtistlyClient(email, password)
client.login()

# Get available styles
styles = client.get_illustrator_styles()
print(f"Available styles: {len(styles)}")

# Generate T-shirt design
result = client.generate_tshirt_images(
    prompts=["A majestic lion wearing a crown"],
    style="36"  # 2D Flat style
)

# Get personal designs
designs = client.get_personal_designs()
print(f"Total designs: {len(designs['designs'])}")

# Download a design
if designs['designs']:
    design_uuid = designs['designs'][0]['uuid']
    client.download_design(design_uuid, "output.png")
```

---

## Security Considerations

### Do NOT:
- Hardcode credentials in code
- Commit credentials to version control
- Share session cookies
- Bypass CSRF protection

### Do:
- Use environment variables for credentials
- Implement proper error handling
- Respect rate limits
- Clear session data after use

---

## Limitations & Unknowns

### Not Documented:
- Complete list of valid agent class names for `/ai-agent` endpoint
- Pagination parameters for `/fetch-personal-designs`
- Complete parameter schemas for all generation endpoints
- Webhook callback URLs (if any)
- API versioning strategy

### Partial Information:
- Full feature set varies by subscription tier
- Some endpoints may require specific product purchases
- Advanced parameters for image generation (resolution, aspect ratio, etc.)

---

## Technical Architecture

- **Backend:** Laravel (PHP framework)
- **Frontend:** Inertia.js (server-side rendering)
- **Authentication:** Laravel Sanctum (session-based)
- **CSRF Protection:** Double-submit cookie pattern
- **CDN:** cdn.artistly.ai (for images and assets)

---

## Changelog

**2026-03-22:**
- Initial documentation
- Tested T-shirt image generation endpoint
- Documented authentication flow
- Listed 223 available routes
- Identified 81+ illustrator styles

---

## Support

This is unofficial reverse-engineered documentation. For official support:
- Website: https://artistly.ai
- App: https://app.artistly.ai

**Disclaimer:** This documentation is provided for educational purposes. Always respect the platform's Terms of Service and usage policies.
