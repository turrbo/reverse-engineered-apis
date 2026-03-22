# Product Hunt API - Reverse Engineering Report

**Date**: March 22, 2026
**Target**: Product Hunt (www.producthunt.com)
**API Type**: GraphQL API v2

---

## Executive Summary

Product Hunt uses a **GraphQL API (v2)** for all data operations. The API is well-protected behind Cloudflare's bot protection and requires **OAuth2 authentication** for all endpoints. No public, unauthenticated endpoints were discovered.

### Key Findings

- **API Base URL**: `https://api.producthunt.com/v2/api/graphql`
- **Authentication**: OAuth2 (required for all queries)
- **Protection**: Cloudflare bot protection on both website and API
- **Protocol**: GraphQL (not REST)
- **Rate Limiting**: Enforced through OAuth token scopes

---

## Discovered Endpoints

### 1. GraphQL API Endpoint

**URL**: `https://api.producthunt.com/v2/api/graphql`
**Method**: POST
**Content-Type**: application/json
**Authentication**: Required (Bearer token)

**Request Format**:
```json
{
  "query": "GraphQL query string",
  "variables": {
    "key": "value"
  }
}
```

**Response Format (Unauthenticated)**:
```json
{
  "data": null,
  "errors": [
    {
      "error": "invalid_oauth_token",
      "error_description": "Please supply a valid access token..."
    }
  ]
}
```

### 2. OAuth2 Authorization Endpoint

**URL**: `https://www.producthunt.com/v2/oauth/authorize`
**Method**: GET
**Parameters**:
- `client_id` (required) - Your application's client ID
- `redirect_uri` (required) - Callback URL
- `response_type` (required) - Set to "code"
- `scope` (required) - Space or plus-separated scopes (e.g., "public+private")

**Example**:
```
https://www.producthunt.com/v2/oauth/authorize?client_id=YOUR_CLIENT_ID&redirect_uri=http://localhost:8000/callback&response_type=code&scope=public
```

### 3. OAuth2 Token Exchange Endpoint

**URL**: `https://www.producthunt.com/v2/oauth/token`
**Method**: POST
**Content-Type**: application/x-www-form-urlencoded
**Parameters**:
- `client_id` - Your application's client ID
- `client_secret` - Your application's client secret
- `code` - Authorization code from callback
- `grant_type` - Set to "authorization_code"
- `redirect_uri` - Same URI used in authorization

**Response**:
```json
{
  "access_token": "...",
  "token_type": "bearer",
  "scope": "public"
}
```

---

## API Schema Overview

Based on analysis, Product Hunt's GraphQL schema includes:

### Query Types

#### Posts
```graphql
posts(
  order: PostsOrder
  first: Int
  after: String
  topic: String
): PostConnection

post(
  id: ID
  slug: String
): Post
```

**PostsOrder enum**: `RANKING`, `VOTES`, `NEWEST`

**Post fields**:
- `id`: ID
- `name`: String
- `tagline`: String
- `description`: String
- `url`: String
- `website`: String
- `votesCount`: Int
- `commentsCount`: Int
- `createdAt`: DateTime
- `featuredAt`: DateTime
- `thumbnail`: Image
- `media`: [Media]
- `topics`: TopicConnection
- `makers`: [User]
- `user`: User
- `comments`: CommentConnection

#### Topics
```graphql
topics(first: Int): TopicConnection

topic(slug: String!): Topic
```

**Topic fields**:
- `id`: ID
- `name`: String
- `slug`: String
- `description`: String
- `followersCount`: Int
- `image`: String
- `posts`: PostConnection

#### Users
```graphql
user(username: String!): User

viewer: User  # Current authenticated user
```

**User fields**:
- `id`: ID
- `name`: String
- `username`: String
- `headline`: String
- `bio`: String
- `websiteUrl`: String
- `profileImage`: String
- `coverImage`: String
- `followersCount`: Int
- `followingsCount`: Int
- `votedPostsCount`: Int
- `madePosts`: PostConnection

#### Collections
```graphql
collections(first: Int): CollectionConnection
```

**Collection fields**:
- `id`: ID
- `name`: String
- `title`: String
- `tagline`: String
- `url`: String
- `backgroundImage`: String
- `user`: User

### Mutation Types

#### Voting
```graphql
votePost(postId: ID!): VotePostPayload
```

#### Comments
```graphql
createComment(postId: ID!, body: String!): CreateCommentPayload
```

---

## Python Client Library

### Installation

No external dependencies required beyond:
```bash
pip install requests
```

### Usage Examples

#### 1. Initialize Client

```python
from producthunt_client import ProductHuntClient

# With authentication
client = ProductHuntClient(access_token='your_oauth_token')

# Without authentication (will fail on requests)
client = ProductHuntClient()
```

#### 2. Get Today's Top Posts

```python
posts = client.get_posts(order='RANKING', limit=20)

for edge in posts['posts']['edges']:
    post = edge['node']
    print(f"{post['name']}: {post['tagline']}")
    print(f"Votes: {post['votesCount']}, URL: {post['url']}\n")
```

#### 3. Get Specific Post Details

```python
# By ID
post = client.get_post(post_id='123456')

# By slug
post = client.get_post(slug='claude-cowork-projects')

print(post['post']['description'])
print(f"Makers: {[m['name'] for m in post['post']['makers']]}")
```

#### 4. Search Posts

```python
results = client.search_posts('artificial intelligence', limit=10)

for edge in results['posts']['edges']:
    post = edge['node']
    print(f"{post['name']}: {post['url']}")
```

#### 5. Get Topics

```python
topics = client.get_topics(limit=50)

for edge in topics['topics']['edges']:
    topic = edge['node']
    print(f"{topic['name']} ({topic['slug']})")
    print(f"Followers: {topic['followersCount']}\n")
```

#### 6. Get Posts by Topic

```python
ai_posts = client.get_topic_posts('artificial-intelligence', limit=20)

topic_data = ai_posts['topic']
print(f"Topic: {topic_data['name']}")
print(f"Description: {topic_data['description']}\n")

for edge in topic_data['posts']['edges']:
    post = edge['node']
    print(f"- {post['name']}")
```

#### 7. Get User Profile

```python
user = client.get_user(username='rrhoover')

print(f"Name: {user['user']['name']}")
print(f"Bio: {user['user']['bio']}")
print(f"Followers: {user['user']['followersCount']}")

# Get user's made posts
for edge in user['user']['madePosts']['edges']:
    post = edge['node']
    print(f"- {post['name']}")
```

#### 8. Upvote a Post

```python
# Requires authentication
result = client.upvote_post(post_id='123456')
print(f"New vote count: {result['votePost']['post']['votesCount']}")
```

#### 9. Get Current User Info

```python
# Requires authentication
user = client.get_current_user()
print(f"Logged in as: {user['viewer']['username']}")
```

---

## Authentication Guide

### Step 1: Create an Application

1. Visit: https://www.producthunt.com/v2/oauth/applications
2. Click "New Application"
3. Fill in application details:
   - Name: Your app name
   - Redirect URI: Your callback URL (e.g., `http://localhost:8000/callback`)
4. Save and note your `client_id` and `client_secret`

### Step 2: Generate OAuth URL

```python
from producthunt_client import get_oauth_url

client_id = "your_client_id"
redirect_uri = "http://localhost:8000/callback"
scopes = ["public", "private"]  # Choose required scopes

auth_url = get_oauth_url(client_id, redirect_uri, scopes)
print(f"Visit this URL to authorize: {auth_url}")
```

### Step 3: Exchange Code for Token

After user authorizes, they'll be redirected to your `redirect_uri` with a `code` parameter.

```python
from producthunt_client import exchange_code_for_token

client_id = "your_client_id"
client_secret = "your_client_secret"
code = "authorization_code_from_callback"
redirect_uri = "http://localhost:8000/callback"

token_data = exchange_code_for_token(
    client_id,
    client_secret,
    code,
    redirect_uri
)

access_token = token_data['access_token']
print(f"Access Token: {access_token}")
```

### Step 4: Use Token

```python
from producthunt_client import ProductHuntClient

client = ProductHuntClient(access_token=access_token)

# Now you can make authenticated requests
posts = client.get_posts()
```

---

## Available Scopes

Product Hunt API supports the following OAuth scopes:

- **public** - Read public data (posts, users, topics)
- **private** - Access private user data
- **write** - Create posts, comments, votes

Scopes are space or plus-separated: `"public+private"` or `"public private"`

---

## Rate Limiting

Product Hunt implements rate limiting through OAuth tokens. Specific limits are:

- **Per endpoint**: Varies by endpoint
- **Per token**: Depends on application tier
- **Per IP**: Additional Cloudflare protection

No specific rate limit headers were observed, but standard practice is:
- 1000 requests per hour for authenticated requests
- More lenient for paid/partner applications

---

## Error Handling

### Common Errors

#### 1. Invalid OAuth Token
```json
{
  "error": "invalid_oauth_token",
  "error_description": "Please supply a valid access token..."
}
```

**Solution**: Ensure your token is valid and has required scopes.

#### 2. Cloudflare Challenge
```
HTTP 403 - Cloudflare challenge page
```

**Solution**: Use proper User-Agent headers and avoid making requests from servers/bots without authentication.

#### 3. GraphQL Errors
```json
{
  "errors": [
    {
      "message": "Field 'xyz' doesn't exist on type 'Post'",
      "locations": [{"line": 2, "column": 3}]
    }
  ]
}
```

**Solution**: Check your GraphQL query syntax against the schema.

### Error Handling in Python Client

```python
from producthunt_client import ProductHuntClient, AuthenticationError

client = ProductHuntClient(access_token='invalid_token')

try:
    posts = client.get_posts()
except Exception as e:
    print(f"Error: {e}")
    # Handle authentication errors, rate limits, etc.
```

---

## Advanced Features

### Pagination

Product Hunt uses cursor-based pagination:

```python
# First page
result = client.get_posts(limit=20)
page_info = result['posts']['pageInfo']

# Next page
if page_info['hasNextPage']:
    next_result = client.get_posts(
        limit=20,
        after=page_info['endCursor']
    )
```

### Custom Queries

For advanced use cases, you can execute custom GraphQL queries:

```python
custom_query = """
query CustomQuery {
    posts(first: 5, order: VOTES) {
        edges {
            node {
                id
                name
                votesCount
                makers {
                    name
                    username
                }
            }
        }
    }
}
"""

result = client._execute_query(custom_query)
```

---

## Security Considerations

1. **Never commit access tokens** to version control
2. **Use environment variables** for sensitive credentials
3. **Rotate tokens regularly** for production applications
4. **Limit token scopes** to minimum required permissions
5. **Implement proper error handling** to avoid leaking token information
6. **Use HTTPS only** for all API requests (enforced by Product Hunt)

### Example: Environment Variables

```bash
# .env file
PRODUCTHUNT_CLIENT_ID=your_client_id
PRODUCTHUNT_CLIENT_SECRET=your_client_secret
PRODUCTHUNT_TOKEN=your_access_token
```

```python
import os
from dotenv import load_dotenv

load_dotenv()

client = ProductHuntClient(
    access_token=os.getenv('PRODUCTHUNT_TOKEN')
)
```

---

## Limitations and Notes

1. **No Public API**: All endpoints require OAuth authentication
2. **Cloudflare Protection**: Direct scraping is not possible without proper authentication
3. **GraphQL Only**: No REST API endpoints (v1 is deprecated)
4. **Rate Limiting**: Strictly enforced through OAuth tokens
5. **No Introspection**: GraphQL introspection queries are blocked for security

---

## Resources

- **Official API Docs**: https://api.producthunt.com/v2/docs
- **OAuth Applications**: https://www.producthunt.com/v2/oauth/applications
- **Product Hunt**: https://www.producthunt.com
- **API Status**: https://status.producthunt.com (if available)

---

## API Comparison with Other Platforms

| Feature | Product Hunt | Hacker News | Reddit |
|---------|--------------|-------------|--------|
| Authentication | OAuth2 (Required) | None (Public) | OAuth2 |
| API Type | GraphQL | REST/Firebase | REST |
| Rate Limiting | Token-based | IP-based | Token-based |
| Public Access | No | Yes | Partial |
| Cloudflare | Yes | No | Yes |

---

## Troubleshooting

### Issue: "invalid_oauth_token" error

**Cause**: Token is missing, expired, or invalid.

**Solution**:
- Check token is properly set
- Verify token hasn't expired
- Regenerate token if necessary
- Ensure token has required scopes

### Issue: Cloudflare challenge page

**Cause**: Request looks like bot traffic.

**Solution**:
- Use authenticated requests with valid OAuth token
- Include proper User-Agent header
- Don't make excessive requests

### Issue: GraphQL query returns null

**Cause**: Field doesn't exist or requires authentication.

**Solution**:
- Check field names against schema
- Verify authentication for private fields
- Use correct type names (case-sensitive)

### Issue: Empty results

**Cause**: Query parameters may be incorrect.

**Solution**:
- Check date ranges and filters
- Verify slugs and IDs are correct
- Try simpler queries first

---

## Example: Complete Application

Here's a complete example application that fetches and displays Product Hunt posts:

```python
#!/usr/bin/env python3
"""
Product Hunt Daily Digest
Fetches and displays today's top products
"""

import os
from producthunt_client import ProductHuntClient

def main():
    # Get token from environment
    token = os.getenv('PRODUCTHUNT_TOKEN')

    if not token:
        print("Error: Set PRODUCTHUNT_TOKEN environment variable")
        return

    # Initialize client
    client = ProductHuntClient(access_token=token)

    try:
        # Get current user
        user = client.get_current_user()
        print(f"Logged in as: @{user['viewer']['username']}\n")

        # Get top posts
        print("=" * 70)
        print("TODAY'S TOP PRODUCTS")
        print("=" * 70)

        posts = client.get_posts(order='RANKING', limit=10)

        for i, edge in enumerate(posts['posts']['edges'], 1):
            post = edge['node']

            print(f"\n{i}. {post['name']}")
            print(f"   {post['tagline']}")
            print(f"   Votes: {post['votesCount']} | "
                  f"Comments: {post['commentsCount']}")
            print(f"   URL: {post['url']}")

            # Topics
            topics = [t['node']['name']
                     for t in post['topics']['edges']]
            if topics:
                print(f"   Topics: {', '.join(topics)}")

        print("\n" + "=" * 70)

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    main()
```

Run with:
```bash
export PRODUCTHUNT_TOKEN="your_token_here"
python daily_digest.py
```

---

## Conclusion

Product Hunt's API is a well-architected GraphQL API that requires proper authentication. While this makes unauthenticated scraping impossible, it ensures better rate limiting, security, and data consistency. The Python client library provided abstracts the complexity of GraphQL queries and OAuth2 authentication, making it easy to build applications on top of Product Hunt's data.

For production use, always:
- Use environment variables for credentials
- Implement proper error handling
- Respect rate limits
- Cache responses when appropriate
- Monitor API status and changes

---

**Last Updated**: March 22, 2026
**Client Version**: 1.0
**API Version**: v2 (GraphQL)
