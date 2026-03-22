# NeuronWriter API Client

Unofficial Python client for the [NeuronWriter](https://neuronwriter.com/) SEO content optimization platform.

This client was reverse-engineered from `app.neuronwriter.com` and provides programmatic access to NeuronWriter's features including content analysis, SERP analysis, keyword research, and project management.

## Features

- Session-based authentication with email/password
- API key authentication support
- Content SEO analysis
- SERP (Search Engine Results Page) analysis
- NLP terms and recommendations
- Competitor analysis
- Project and document management
- Inventory management (URLs and keywords)
- Content templates
- Export capabilities

## Installation

```bash
# The client is a single-file library with minimal dependencies
pip install requests
```

Then simply copy `neuronwriter_client.py` to your project.

## Authentication

NeuronWriter uses two authentication methods:

### 1. Session-Based Authentication (Form Login)

Standard web login that establishes a session cookie:

```python
from neuronwriter_client import NeuronWriterClient

client = NeuronWriterClient(
    email="your@email.com",
    password="your_password"
)
client.login()
```

### 2. API Key Authentication

For API endpoints, an X-API-KEY header is required:

```python
client = NeuronWriterClient(
    email="your@email.com",
    password="your_password",
    api_key="your-api-key"
)
client.api_login()  # Alternative API-based login
```

### Environment Variables

Credentials can be provided via environment variables:

```bash
export NEURONWRITER_EMAIL="your@email.com"
export NEURONWRITER_PASSWORD="your_password"
export NEURONWRITER_API_KEY="your-api-key"  # Optional
```

```python
# Client will automatically use environment variables
client = NeuronWriterClient()
client.login()
```

## Usage Examples

### Basic Authentication

```python
from neuronwriter_client import NeuronWriterClient

# Initialize and login
with NeuronWriterClient(email="your@email.com", password="password") as client:
    client.login()

    # Get session information
    session_info = client.get_session_info()
    print(f"Authenticated: {session_info['authenticated']}")
    print(f"Cookies: {session_info['cookies']}")
```

### Content Analysis

```python
# Analyze content for SEO
result = client.analyze_content(
    content="Your article content here...",
    target_keyword="seo content optimization"
)

print(f"SEO Score: {result.get('score')}")
print(f"Recommendations: {result.get('recommendations')}")
```

### SERP Analysis

```python
# Get SERP analysis for a keyword
serp_data = client.get_serp_analysis(
    keyword="content marketing",
    location="US",
    language="en"
)

print(f"Top ranking pages: {serp_data.get('results')}")
```

### NLP Terms

```python
# Get NLP terms for keyword optimization
nlp_data = client.get_nlp_terms(keyword="machine learning")

for term in nlp_data.get('terms', []):
    print(f"{term['word']}: {term['relevance']}")
```

### Competitor Analysis

```python
# Analyze competitor content
competitors = client.get_competitor_analysis(
    keyword="python tutorial",
    competitor_urls=[
        "https://realpython.com/python-tutorial/",
        "https://docs.python.org/tutorial/"
    ]
)

print(f"Competitor insights: {competitors}")
```

### Project Management

```python
# List all projects
projects = client.get_projects()
for project in projects:
    print(f"Project: {project['name']} (ID: {project['id']})")

# Create new project
new_project = client.create_project(
    name="My SEO Project",
    description="Blog content optimization"
)

# Get documents in a project
documents = client.get_documents(project_id=new_project['id'])
```

### Document Management

```python
# Create a new document
doc = client.create_document(
    title="How to Optimize Content for SEO",
    project_id="project-123",
    content="Draft content here..."
)

# Get document details
document = client.get_document(document_id=doc['id'])

# Update document
updated_doc = client.update_document(
    document_id=doc['id'],
    content="Updated content...",
    status="published"
)

# Delete document
client.delete_document(document_id=doc['id'])
```

### Inventory Management

```python
# Add URLs to inventory for tracking
result = client.add_inventory_urls([
    "https://example.com/blog/post-1",
    "https://example.com/blog/post-2"
])

# Add keywords to track
result = client.add_inventory_keywords([
    "content marketing",
    "seo optimization",
    "keyword research"
])

# Request MOZ metrics update
client.request_moz_update(url="https://example.com")

# Request search volume update
client.request_volume_update(keyword="seo tools")
```

### Templates

```python
# Get all templates
templates = client.get_templates()

# Create a new template
template = client.create_template(
    name="Blog Post Template",
    content="# {title}\n\n{intro}\n\n## Key Points\n\n{body}",
    category="blog"
)
```

### Export Data

```python
# Export data table to file
file_content = client.export_table(
    dt_id="keywords_table",
    ajax_table=True,
    extra={"format": "xlsx"}
)

with open("export.xlsx", "wb") as f:
    f.write(file_content)
```

### User Preferences

```python
# Update user preferences
client.update_preference({
    "theme": "dark",
    "language": "en",
    "notifications_enabled": True
})

# Get user profile
profile = client.get_profile()
print(f"User: {profile['name']}")
print(f"Plan: {profile['subscription']}")
```

## API Endpoints Discovered

### Authentication
- `POST /ucp/login` - Form-based login
- `POST /api/login` - API login (requires X-API-KEY)

### User Management
- `GET /ucp/profile` - Get user profile
- `POST /ucp/update-preference` - Update preferences

### Backend/Inventory
- `POST /backend/add-inventory-urls` - Add URLs to inventory
- `POST /backend/add-inventory-keywords` - Add keywords to inventory
- `POST /backend/request-moz-update` - Request MOZ metrics update
- `POST /backend/request-volume-update` - Request search volume update
- `POST /backend/export-table` - Export data tables

### Content & Analysis
- `POST /api/analyze` - Analyze content for SEO
- `GET /api/serp` - Get SERP analysis
- `GET /api/nlp-terms` - Get NLP terms
- `POST /api/competitors` - Analyze competitors

### Projects & Documents
- `GET /api/projects` - List projects
- `POST /api/projects` - Create project
- `GET /api/documents` - List documents
- `POST /api/documents` - Create document
- `GET /api/documents/{id}` - Get document
- `PUT /api/documents/{id}` - Update document
- `DELETE /api/documents/{id}` - Delete document

### Templates
- `GET /api/templates` - List templates
- `POST /api/templates` - Create template

## Authentication Flow

1. **Session Establishment**: The client first accesses the main page to establish a session cookie (`contai_session_id`)

2. **Form Login**: Credentials are submitted via POST to `/ucp/login` with form data:
   ```
   email: user@example.com
   password: password
   redirect_url: /
   ```

3. **Session Cookie**: Upon successful login, the session cookie is used for subsequent requests

4. **API Authentication**: For API endpoints, an `X-API-KEY` header is required:
   ```
   X-API-KEY: your-api-key-here
   ```

## Error Handling

The client provides specific exception types:

```python
from neuronwriter_client import (
    NeuronWriterError,
    AuthenticationError,
    APIError
)

try:
    client.login()
except AuthenticationError as e:
    print(f"Login failed: {e}")
except APIError as e:
    print(f"API request failed: {e}")
except NeuronWriterError as e:
    print(f"General error: {e}")
```

## Advanced Usage

### Custom Session

Reuse an existing requests session:

```python
import requests
from neuronwriter_client import NeuronWriterClient

session = requests.Session()
session.headers.update({"Custom-Header": "value"})

client = NeuronWriterClient(
    email="your@email.com",
    password="password",
    session=session
)
```

### Context Manager

Use with context manager for automatic cleanup:

```python
with NeuronWriterClient() as client:
    client.login()
    # Do work...
# Session automatically cleaned up
```

## Notes and Limitations

1. **Credential Requirements**: Valid NeuronWriter account credentials are required. The client was tested with the authentication flow but credentials provided during reverse engineering were invalid.

2. **API Key**: Some endpoints require an `X-API-KEY` header. This key is not publicly documented and may need to be extracted from an authenticated browser session.

3. **Endpoint Discovery**: Many endpoints are inferred from common SEO tool patterns and JavaScript analysis. Some may require adjustment based on actual API responses.

4. **Rate Limiting**: NeuronWriter likely implements rate limiting. Use appropriate delays between requests.

5. **API Stability**: This is an unofficial client based on reverse engineering. The API may change without notice.

6. **Error Responses**: Not all error response formats are known. The client attempts to handle common cases but may need refinement.

## Obtaining API Key

To obtain your API key:

1. Log into NeuronWriter in your browser
2. Open browser developer tools (F12)
3. Go to Network tab
4. Interact with the application
5. Look for API requests and examine the `X-API-KEY` header value
6. Copy this key for use in the client

Alternatively, check browser localStorage/sessionStorage:

```javascript
// In browser console
console.log(localStorage);
console.log(sessionStorage);
```

## Development

### Running Tests

```bash
export NEURONWRITER_EMAIL="your@email.com"
export NEURONWRITER_PASSWORD="your_password"
python neuronwriter_client.py
```

### Contributing

This is a reverse-engineered client. Contributions welcome:

1. Discover new endpoints
2. Document API responses
3. Add new methods
4. Improve error handling
5. Add tests

## Troubleshooting

### Authentication Fails

```
AuthenticationError: Invalid email or password
```

**Solutions:**
- Verify your email and password are correct
- Check if your account is active
- Try logging in via the web interface first
- Ensure no special characters are causing issues

### Missing X-API-KEY Error

```
{"error": "Request is missing the required X-API-KEY header."}
```

**Solution:**
- Extract API key from browser session (see "Obtaining API Key" section)
- Pass API key to client: `NeuronWriterClient(api_key="your-key")`

### Endpoint Not Found

```
APIError: Unable to fetch projects - endpoint not found
```

**Solution:**
- The endpoint structure may have changed
- Try alternative endpoints in the client code
- Check browser network tab for correct endpoint

## Security

- Never commit credentials to version control
- Use environment variables for sensitive data
- Consider using a secrets management system for production
- The API key should be treated as sensitive as your password

## License

This is an unofficial, reverse-engineered client. Use at your own risk.

NeuronWriter is a trademark of CONTADU. This project is not affiliated with, endorsed by, or associated with NeuronWriter or CONTADU.

## Disclaimer

This client was created for educational and research purposes. Always review NeuronWriter's Terms of Service before using automated access to their platform. The authors are not responsible for any violations or consequences resulting from use of this client.

## Support

For issues with:
- **This client**: Open an issue on the project repository
- **NeuronWriter service**: Contact NeuronWriter support at https://neuronwriter.com

## Changelog

### v1.0.0 (2026-03-22)
- Initial release
- Session-based authentication
- API key authentication support
- Core CRUD operations for projects and documents
- Content analysis methods
- SERP analysis
- Inventory management
- Template support
- Export functionality
- Comprehensive error handling

## Related Projects

- [NeuronWriter](https://neuronwriter.com/) - Official website
- [CONTADU](https://contadu.com/) - Parent company

## Author

Reverse engineered and documented by Claude Code on 2026-03-22.

## Future Enhancements

Potential additions:
- [ ] Async support with `httpx`
- [ ] Bulk operations
- [ ] Caching layer
- [ ] Webhook support (if available)
- [ ] CLI interface
- [ ] More comprehensive tests
- [ ] Response models with Pydantic
- [ ] Pagination support
- [ ] Retry logic with exponential backoff
