"""
Product Hunt API Client
========================

A Python client for interacting with Product Hunt's GraphQL API (v2).

Product Hunt requires OAuth2 authentication for API access. To use this client:

1. Create an app at https://www.producthunt.com/v2/oauth/applications
2. Get your API key and secret
3. Generate an access token using OAuth2 flow

API Documentation: https://api.producthunt.com/v2/docs

Note: Product Hunt's API is protected by Cloudflare and requires proper authentication.
"""

import requests
from typing import Dict, List, Optional, Any
from datetime import datetime
import json


class ProductHuntClient:
    """Client for Product Hunt API v2 (GraphQL)."""

    BASE_URL = "https://api.producthunt.com/v2/api/graphql"

    def __init__(self, access_token: Optional[str] = None):
        """
        Initialize the Product Hunt API client.

        Args:
            access_token: OAuth2 access token. Required for authenticated requests.
        """
        self.session = requests.Session()
        self.access_token = access_token

        # Set default headers
        self.session.headers.update({
            'Content-Type': 'application/json',
            'Accept': 'application/json',
            'User-Agent': 'ProductHunt-Python-Client/1.0'
        })

        if self.access_token:
            self.session.headers.update({
                'Authorization': f'Bearer {self.access_token}'
            })

    def _execute_query(self, query: str, variables: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Execute a GraphQL query.

        Args:
            query: GraphQL query string
            variables: Optional variables for the query

        Returns:
            Response data as dictionary

        Raises:
            Exception: If the request fails or returns errors
        """
        payload = {'query': query}
        if variables:
            payload['variables'] = variables

        response = self.session.post(self.BASE_URL, json=payload)

        if response.status_code != 200:
            raise Exception(f"HTTP {response.status_code}: {response.text}")

        data = response.json()

        if 'errors' in data and data['errors']:
            error_messages = []
            for error in data['errors']:
                if isinstance(error, dict):
                    if 'error' in error:
                        error_messages.append(f"{error.get('error')}: {error.get('error_description', '')}")
                    elif 'message' in error:
                        error_messages.append(error['message'])
                else:
                    error_messages.append(str(error))
            raise Exception(f"GraphQL errors: {'; '.join(error_messages)}")

        return data.get('data', {})

    def get_posts(self, order: str = "RANKING", limit: int = 20, after: Optional[str] = None) -> Dict[str, Any]:
        """
        Get a list of posts.

        Args:
            order: Sort order (RANKING, VOTES, NEWEST)
            limit: Number of posts to fetch (max 100)
            after: Cursor for pagination

        Returns:
            Posts data with edges and pageInfo
        """
        query = """
        query Posts($order: PostsOrder, $first: Int, $after: String) {
            posts(order: $order, first: $first, after: $after) {
                edges {
                    node {
                        id
                        name
                        tagline
                        description
                        url
                        votesCount
                        commentsCount
                        createdAt
                        featuredAt
                        website
                        thumbnail {
                            url
                        }
                        topics {
                            edges {
                                node {
                                    id
                                    name
                                    slug
                                }
                            }
                        }
                        user {
                            id
                            name
                            username
                            headline
                        }
                    }
                }
                pageInfo {
                    hasNextPage
                    hasPreviousPage
                    startCursor
                    endCursor
                }
            }
        }
        """

        variables = {
            'order': order,
            'first': limit
        }

        if after:
            variables['after'] = after

        return self._execute_query(query, variables)

    def get_post(self, post_id: Optional[str] = None, slug: Optional[str] = None) -> Dict[str, Any]:
        """
        Get details of a specific post.

        Args:
            post_id: Post ID
            slug: Post slug (alternative to post_id)

        Returns:
            Post details
        """
        if not post_id and not slug:
            raise ValueError("Either post_id or slug must be provided")

        query = """
        query Post($id: ID, $slug: String) {
            post(id: $id, slug: $slug) {
                id
                name
                tagline
                description
                url
                votesCount
                commentsCount
                createdAt
                featuredAt
                website
                thumbnail {
                    url
                }
                media {
                    url
                    type
                }
                topics {
                    edges {
                        node {
                            id
                            name
                            slug
                        }
                    }
                }
                makers {
                    id
                    name
                    username
                    headline
                    profileImage
                }
                user {
                    id
                    name
                    username
                    headline
                    profileImage
                }
                comments {
                    edges {
                        node {
                            id
                            body
                            createdAt
                            user {
                                id
                                name
                                username
                            }
                        }
                    }
                }
            }
        }
        """

        variables = {}
        if post_id:
            variables['id'] = post_id
        if slug:
            variables['slug'] = slug

        return self._execute_query(query, variables)

    def search_posts(self, query_text: str, limit: int = 20) -> Dict[str, Any]:
        """
        Search for posts.

        Args:
            query_text: Search query
            limit: Number of results

        Returns:
            Search results
        """
        query = """
        query SearchPosts($query: String!, $first: Int) {
            posts(order: RANKING, first: $first, topic: $query) {
                edges {
                    node {
                        id
                        name
                        tagline
                        url
                        votesCount
                        website
                        thumbnail {
                            url
                        }
                    }
                }
            }
        }
        """

        variables = {
            'query': query_text,
            'first': limit
        }

        return self._execute_query(query, variables)

    def get_topics(self, limit: int = 50) -> Dict[str, Any]:
        """
        Get list of topics/categories.

        Args:
            limit: Number of topics to fetch

        Returns:
            Topics data
        """
        query = """
        query Topics($first: Int) {
            topics(first: $first) {
                edges {
                    node {
                        id
                        name
                        slug
                        description
                        followersCount
                        image
                    }
                }
            }
        }
        """

        variables = {'first': limit}
        return self._execute_query(query, variables)

    def get_topic_posts(self, topic_slug: str, limit: int = 20) -> Dict[str, Any]:
        """
        Get posts for a specific topic.

        Args:
            topic_slug: Topic slug (e.g., 'artificial-intelligence')
            limit: Number of posts

        Returns:
            Posts in the topic
        """
        query = """
        query TopicPosts($slug: String!, $first: Int) {
            topic(slug: $slug) {
                id
                name
                description
                posts(first: $first) {
                    edges {
                        node {
                            id
                            name
                            tagline
                            url
                            votesCount
                            thumbnail {
                                url
                            }
                        }
                    }
                }
            }
        }
        """

        variables = {
            'slug': topic_slug,
            'first': limit
        }

        return self._execute_query(query, variables)

    def get_user(self, username: str) -> Dict[str, Any]:
        """
        Get user profile information.

        Args:
            username: Product Hunt username

        Returns:
            User profile data
        """
        query = """
        query User($username: String!) {
            user(username: $username) {
                id
                name
                username
                headline
                bio
                websiteUrl
                profileImage
                coverImage
                followersCount
                followingsCount
                votedPostsCount
                madePosts {
                    edges {
                        node {
                            id
                            name
                            tagline
                            url
                            thumbnail {
                                url
                            }
                        }
                    }
                }
            }
        }
        """

        variables = {'username': username}
        return self._execute_query(query, variables)

    def get_collections(self, limit: int = 20) -> Dict[str, Any]:
        """
        Get featured collections.

        Args:
            limit: Number of collections

        Returns:
            Collections data
        """
        query = """
        query Collections($first: Int) {
            collections(first: $first) {
                edges {
                    node {
                        id
                        name
                        title
                        tagline
                        url
                        backgroundImage
                        user {
                            id
                            name
                            username
                        }
                    }
                }
            }
        }
        """

        variables = {'first': limit}
        return self._execute_query(query, variables)

    def upvote_post(self, post_id: str) -> Dict[str, Any]:
        """
        Upvote a post (requires authentication).

        Args:
            post_id: ID of the post to upvote

        Returns:
            Vote data
        """
        query = """
        mutation VotePost($postId: ID!) {
            votePost(postId: $postId) {
                post {
                    id
                    votesCount
                }
            }
        }
        """

        variables = {'postId': post_id}
        return self._execute_query(query, variables)

    def get_current_user(self) -> Dict[str, Any]:
        """
        Get current authenticated user's information.

        Returns:
            Current user data
        """
        query = """
        query Viewer {
            viewer {
                id
                name
                username
                headline
                bio
                profileImage
                websiteUrl
            }
        }
        """

        return self._execute_query(query)


class ProductHuntError(Exception):
    """Base exception for Product Hunt API errors."""
    pass


class AuthenticationError(ProductHuntError):
    """Raised when authentication fails."""
    pass


class RateLimitError(ProductHuntError):
    """Raised when rate limit is exceeded."""
    pass


def get_oauth_url(client_id: str, redirect_uri: str, scopes: List[str] = None) -> str:
    """
    Generate OAuth authorization URL.

    Args:
        client_id: Your application's client ID
        redirect_uri: Redirect URI after authorization
        scopes: List of scopes (e.g., ['public', 'private'])

    Returns:
        Authorization URL
    """
    if scopes is None:
        scopes = ['public']

    scope_str = '+'.join(scopes)
    return (
        f"https://www.producthunt.com/v2/oauth/authorize"
        f"?client_id={client_id}"
        f"&redirect_uri={redirect_uri}"
        f"&response_type=code"
        f"&scope={scope_str}"
    )


def exchange_code_for_token(client_id: str, client_secret: str, code: str, redirect_uri: str) -> Dict[str, str]:
    """
    Exchange authorization code for access token.

    Args:
        client_id: Your application's client ID
        client_secret: Your application's client secret
        code: Authorization code from OAuth callback
        redirect_uri: Same redirect URI used in authorization

    Returns:
        Token response with access_token
    """
    url = "https://www.producthunt.com/v2/oauth/token"

    data = {
        'client_id': client_id,
        'client_secret': client_secret,
        'code': code,
        'grant_type': 'authorization_code',
        'redirect_uri': redirect_uri
    }

    response = requests.post(url, data=data)
    response.raise_for_status()

    return response.json()


if __name__ == "__main__":
    """
    Example usage of the Product Hunt API client.

    Note: Most endpoints require authentication. Set your access token
    in the PRODUCTHUNT_TOKEN environment variable or pass it directly.
    """

    import os

    # Get access token from environment variable
    access_token = os.environ.get('PRODUCTHUNT_TOKEN')

    if not access_token:
        print("=" * 70)
        print("Product Hunt API Client - Demo")
        print("=" * 70)
        print("\nNOTE: Product Hunt API requires OAuth2 authentication.")
        print("To use this client, you need to:")
        print("1. Create an app at: https://www.producthunt.com/v2/oauth/applications")
        print("2. Get your API credentials")
        print("3. Generate an access token")
        print("4. Set PRODUCTHUNT_TOKEN environment variable")
        print("\nAPI Endpoints discovered:")
        print("- GraphQL API: https://api.producthunt.com/v2/api/graphql")
        print("- OAuth Authorization: https://www.producthunt.com/v2/oauth/authorize")
        print("- Token Exchange: https://www.producthunt.com/v2/oauth/token")
        print("\n" + "=" * 70)
        print("\nExample: Generate OAuth URL")
        print("=" * 70)

        # Example OAuth URL generation (requires your client_id)
        example_client_id = "YOUR_CLIENT_ID"
        example_redirect = "http://localhost:8000/callback"
        oauth_url = get_oauth_url(example_client_id, example_redirect, ['public'])
        print(f"\nOAuth URL: {oauth_url}")

        print("\n" + "=" * 70)
        print("Client API Methods Available:")
        print("=" * 70)
        print("\nPosts:")
        print("  - get_posts(order='RANKING', limit=20)")
        print("  - get_post(post_id='...' or slug='...')")
        print("  - search_posts(query_text='AI', limit=20)")
        print("\nTopics:")
        print("  - get_topics(limit=50)")
        print("  - get_topic_posts(topic_slug='artificial-intelligence')")
        print("\nUsers:")
        print("  - get_user(username='chrismessina')")
        print("  - get_current_user()")
        print("\nCollections:")
        print("  - get_collections(limit=20)")
        print("\nInteractions (requires auth):")
        print("  - upvote_post(post_id='...')")

        print("\n" + "=" * 70)
        print("Example Usage with Token:")
        print("=" * 70)
        print("""
# Initialize client with token
client = ProductHuntClient(access_token='your_token_here')

# Get today's top posts
posts = client.get_posts(order='RANKING', limit=10)
for edge in posts['posts']['edges']:
    post = edge['node']
    print(f"{post['name']}: {post['tagline']}")

# Get specific post
post = client.get_post(slug='claude-cowork-projects')
print(post['post']['description'])

# Get user profile
user = client.get_user(username='rrhoover')
print(user['user']['bio'])

# Search posts
results = client.search_posts('artificial intelligence')

# Get topics
topics = client.get_topics(limit=20)
""")
    else:
        # If token is available, run actual API calls
        print("=" * 70)
        print("Product Hunt API Client - Live Demo")
        print("=" * 70)

        client = ProductHuntClient(access_token=access_token)

        try:
            print("\n1. Fetching current user...")
            user = client.get_current_user()
            print(f"   Logged in as: {user.get('viewer', {}).get('username', 'N/A')}")

            print("\n2. Fetching top posts...")
            posts = client.get_posts(order='RANKING', limit=5)
            for i, edge in enumerate(posts.get('posts', {}).get('edges', [])[:5], 1):
                post = edge['node']
                print(f"   {i}. {post['name']} - {post['tagline']}")
                print(f"      Votes: {post['votesCount']}, Comments: {post['commentsCount']}")

            print("\n3. Fetching topics...")
            topics = client.get_topics(limit=5)
            for i, edge in enumerate(topics.get('topics', {}).get('edges', [])[:5], 1):
                topic = edge['node']
                print(f"   {i}. {topic['name']} ({topic['slug']})")

        except Exception as e:
            print(f"\nError: {e}")
            print("\nMake sure your access token is valid and has the required scopes.")
