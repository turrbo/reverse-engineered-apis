# Taja.ai API Client

Unofficial Python client for the Taja.ai API - A YouTube optimization and content AI tool.

## ⚠️ Important Notice

**This is a TEMPLATE client.** The actual API endpoints for Taja.ai need to be discovered through manual browser inspection, as the platform uses a complex Next.js SPA architecture with client-side authentication.

### Why Manual Discovery is Required

1. **Client-Side Authentication**: Taja.ai uses a Next.js Single Page Application (SPA) with client-side rendering
2. **Form Validation**: The login button is disabled until client-side validation completes
3. **Bot Detection**: Automated browsers may be detected and redirected
4. **Unknown Auth Provider**: The authentication system (NextAuth, Supabase, Firebase, Auth0, etc.) needs to be identified

## Manual API Discovery

See `TAJA_MANUAL_INSTRUCTIONS.md` for detailed instructions on discovering the API endpoints manually using browser DevTools.

### Quick Manual Discovery Steps

1. Open Chrome DevTools (F12)
2. Go to Network tab → Filter by Fetch/XHR
3. Navigate to https://app.taja.ai/signin
4. Enter credentials and login
5. Observe network requests to identify:
   - Authentication endpoint
   - Bearer tokens or session cookies
   - API base URL
   - Available endpoints

## Installation

```bash
# Clone/download the client
cd outputs

# Install dependencies
pip install requests

# Set credentials as environment variables (DO NOT hardcode)
export TAJA_EMAIL="your-email@example.com"
export TAJA_PASSWORD="your-password"
```

## Usage (Once Endpoints Are Discovered)

```python
from taja_client import TajaClient

# Initialize client with credentials from environment variables
client = TajaClient()

# Or pass credentials directly (not recommended)
# client = TajaClient(email="your-email", password="your-password")

# Login
if client.login():
    print("Logged in successfully!")

    # Get user profile
    profile = client.get_user_profile()
    print(f"User: {profile}")

    # Analyze a YouTube video
    video_url = "https://www.youtube.com/watch?v=VIDEO_ID"
    analysis = client.analyze_video(video_url)
    print(f"Analysis: {analysis}")

    # Get title suggestions
    titles = client.get_title_suggestions("VIDEO_ID")
    print(f"Title suggestions: {titles}")

    # Get description suggestions
    descriptions = client.get_description_suggestions("VIDEO_ID")
    print(f"Description suggestions: {descriptions}")

    # Get tag suggestions
    tags = client.get_tag_suggestions("VIDEO_ID")
    print(f"Tag suggestions: {tags}")

    # Analyze thumbnail
    thumbnail_analysis = client.analyze_thumbnail(
        "https://i.ytimg.com/vi/VIDEO_ID/maxresdefault.jpg"
    )
    print(f"Thumbnail analysis: {thumbnail_analysis}")

    # Get channel analytics
    analytics = client.get_channel_analytics("CHANNEL_ID")
    print(f"Analytics: {analytics}")

    # Get trending topics
    trends = client.get_trending_topics(category="tech")
    print(f"Trending: {trends}")

    # Create content plan
    plan = client.create_content_plan({
        "niche": "technology",
        "frequency": "weekly",
        "goals": ["grow subscribers", "increase engagement"]
    })
    print(f"Content plan: {plan}")
```

## Expected Features (Based on Taja.ai Marketing)

Once the API is fully discovered, this client should support:

### Video Optimization
- **Title Generation**: AI-powered title suggestions optimized for CTR
- **Description Writing**: SEO-optimized video descriptions
- **Tag Suggestions**: Relevant tags based on content and trends
- **Thumbnail Analysis**: Feedback on thumbnail effectiveness

### Analytics & Insights
- **Channel Performance**: Track views, engagement, subscriber growth
- **Video Performance**: Individual video metrics and insights
- **Competitor Analysis**: Compare with similar channels
- **Trend Identification**: Discover trending topics in your niche

### Content Planning
- **Content Calendar**: Plan and schedule content
- **Topic Research**: Find high-performing content ideas
- **SEO Recommendations**: Keyword suggestions and optimization tips
- **Viral Prediction**: Estimate potential video performance

### Automation Features
- **Shorts Generation**: Convert long videos to shorts
- **Clip Creation**: Auto-generate clips with captions
- **Multi-Platform Publishing**: Schedule to YouTube, TikTok, Instagram
- **Batch Processing**: Optimize multiple videos at once

## Known Platform Details

### Technology Stack
- **Frontend**: Next.js with Server-Side Rendering (SSR)
- **Analytics**: Google Tag Manager, Amplitude, Customer.io
- **Hosting**: Vercel with Cloudflare CDN

### Base URLs
- Main app: `https://app.taja.ai`
- Possible API: `https://api.taja.ai` (to be confirmed)
- Marketing site: `https://www.taja.ai`

### Authentication
Login page: `https://app.taja.ai/signin`
- Email/password authentication
- Possible Google OAuth option
- Unknown backend (NextAuth, Supabase, Firebase, Auth0, or custom)

## Environment Variables

```bash
# Required
export TAJA_EMAIL="your-email@example.com"
export TAJA_PASSWORD="your-password"

# Optional (if you discover API keys/tokens)
# export TAJA_API_KEY="your-api-key"
```

## Security Notes

- **Never hardcode credentials** in your code
- Use environment variables for sensitive data
- The template client uses environment variables by default
- Be careful not to commit `.env` files to version control

## API Rate Limits

Rate limits are unknown and need to be discovered. Monitor response headers for:
- `X-RateLimit-Limit`
- `X-RateLimit-Remaining`
- `X-RateLimit-Reset`
- `Retry-After`

## Error Handling

The client includes basic error handling, but specific error codes and messages need to be discovered:

```python
try:
    result = client.analyze_video("VIDEO_ID")
except requests.exceptions.HTTPError as e:
    print(f"HTTP Error: {e.response.status_code}")
    print(f"Message: {e.response.json()}")
except requests.exceptions.RequestException as e:
    print(f"Request failed: {e}")
```

## Contributing to Discovery

If you discover actual API endpoints, please update:

1. The endpoint URLs in `taja_client.py`
2. Request/response formats
3. Authentication flow
4. Rate limits
5. Error codes
6. This README with findings

## Current Status

- ✅ Template client created with expected methods
- ✅ Authentication flow structure
- ⚠️ **API endpoints need manual discovery**
- ⚠️ **Authentication mechanism needs identification**
- ⚠️ **Request/response formats need validation**
- ⚠️ **Rate limits unknown**

## Next Steps

1. Follow `TAJA_MANUAL_INSTRUCTIONS.md` to discover endpoints
2. Test discovered endpoints with curl or Postman
3. Update `taja_client.py` with real endpoints
4. Validate request/response formats
5. Add proper error handling for discovered error codes
6. Test all methods
7. Document rate limits and best practices

## Disclaimer

This is an unofficial client created through reverse engineering. It is not affiliated with, endorsed by, or supported by Taja.ai. Use at your own risk and in accordance with Taja.ai's Terms of Service.

## Troubleshooting

### Login Fails
- Verify credentials are correct
- Check if account is active
- Ensure no 2FA/MFA is enabled (or handle it)
- Look for CAPTCHA requirements
- Check for IP-based restrictions

### Endpoints Return 404
- Endpoints are templates and need to be discovered
- Check browser DevTools for actual URLs
- API base URL may be different

### Bot Detection
- Use proper User-Agent headers
- Respect rate limits
- Add delays between requests
- Consider using session cookies from manual login

## License

MIT License - See LICENSE file for details

## Support

For issues with this client, please see `TAJA_MANUAL_INSTRUCTIONS.md` for guidance on completing the API discovery process.

For issues with Taja.ai service itself, contact Taja.ai support.
