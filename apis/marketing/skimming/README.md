# Skimming AI API Client

## Overview

This repository contains a Python client for interacting with Skimming AI (which redirects to NEURONwriter.com). The client provides a simple interface for authentication and API interactions.

## Important Discovery

During reverse engineering, it was discovered that:
- **app.skimming.ai** redirects to **app.neuronwriter.com**
- The service appears to have been rebranded from Skimming AI to NEURONwriter
- The login page also showed various redirects to **app.taja.ai** at different times
- These services appear to be related or part of the same platform

## Authentication Issues

**Note:** The provided credentials were not valid for the current NEURONwriter platform. The login attempt returned:
```
"The e-mail and password don't match."
```

This could mean:
1. The account doesn't exist on the current platform
2. The credentials have changed
3. The account was migrated and needs to be re-activated
4. The service requires different authentication

## Installation

```bash
pip install requests
```

## Configuration

The client requires authentication credentials. Set them as environment variables:

```bash
export SKIMMING_EMAIL="your-email@example.com"
export SKIMMING_PASSWORD="your-password"
```

Alternatively, pass them directly to the client constructor.

## Usage

### Basic Example

```python
from skimming_client import SkimmingClient

# Initialize client (reads from environment variables)
client = SkimmingClient()

# Or provide credentials explicitly
client = SkimmingClient(
    email="your-email@example.com",
    password="your-password"
)

# Login
auth_response = client.login()
print(f"Logged in as: {client.user_data}")

# Get user profile
profile = client.get_user_profile()
print(profile)

# Get documents
documents = client.get_documents()
print(documents)

# Create a new document
new_doc = client.create_document(
    title="My Document",
    content="Document content here"
)
print(new_doc)

# Summarize text
summary = client.summarize_text("Long text to summarize...")
print(summary)

# Analyze URL
analysis = client.analyze_url("https://example.com/article")
print(analysis)
```

### Command Line Usage

```bash
# Set credentials
export SKIMMING_EMAIL="your-email@example.com"
export SKIMMING_PASSWORD="your-password"

# Run the client
python skimming_client.py
```

## API Endpoints

Based on observation and common patterns, the following endpoints were identified:

### Authentication

- **POST** `/api/login`
  - Payload: `{ "email": "...", "password": "..." }`
  - Returns: Authentication token and user data

### User Management

- **GET** `/api/user/profile`
  - Returns: User profile information

### Documents

- **GET** `/api/documents`
  - Returns: List of user's documents

- **POST** `/api/documents`
  - Payload: `{ "title": "...", "content": "..." }`
  - Returns: Created document

- **GET** `/api/documents/{id}`
  - Returns: Specific document

### Content Processing

- **POST** `/api/summarize`
  - Payload: `{ "text": "...", ...options }`
  - Returns: Text summary

- **POST** `/api/analyze`
  - Payload: `{ "url": "..." }`
  - Returns: URL content analysis

## Architecture Notes

### Domain Redirects

The service architecture shows interesting redirect patterns:
1. `app.skimming.ai` → `app.neuronwriter.com`
2. Some requests also redirect to `app.taja.ai`

This suggests a multi-product platform or rebranding.

### API Structure

- Base URL: `https://app.neuronwriter.com`
- API prefix: `/api/`
- Authentication: Bearer token in Authorization header
- Content-Type: `application/json`

### Network Observations

During testing, the following was observed:
- Modern React-based SPA (Single Page Application)
- Uses Next.js framework
- Form submissions use fetch API
- Analytics integrations: Google Tag Manager, Clarity

## Limitations

1. **Authentication Required**: All API endpoints require valid authentication
2. **Credentials Not Validated**: The provided test credentials did not work
3. **Incomplete Endpoint Discovery**: Without successful login, comprehensive endpoint mapping was not possible
4. **Endpoint URLs Are Estimated**: Some endpoints in the client are based on common REST API patterns and may not exist

## Security Notes

- **Never commit credentials** to version control
- Always use environment variables for sensitive data
- The client validates that credentials are provided before making requests
- HTTPS is used for all communications

## Troubleshooting

### Authentication Fails

If you get "The e-mail and password don't match":
1. Verify your credentials are correct
2. Check if you need to activate your account
3. Try resetting your password on the NEURONwriter website
4. Contact support if the issue persists

### Domain Redirects

If you see unexpected redirects:
- The service may have multiple domains
- Use the final redirect URL (app.neuronwriter.com) directly
- Check for service announcements about rebranding

### Import Errors

Make sure you have requests installed:
```bash
pip install requests
```

## Future Work

To complete the API reverse engineering:
1. Obtain valid credentials for the platform
2. Perform authenticated session exploration
3. Map all available endpoints
4. Document request/response schemas
5. Add error handling for specific API error codes
6. Implement rate limiting
7. Add response models/types

## License

This client is provided as-is for educational and integration purposes.

## Support

For issues with:
- **This client code**: Open an issue in this repository
- **The Skimming AI / NEURONwriter service**: Contact their support directly

## Related Services

Based on the redirects observed:
- NEURONwriter: https://app.neuronwriter.com/
- Taja AI: https://app.taja.ai/
- CONTADU: Appears to be the parent company (powering NEURONwriter)
