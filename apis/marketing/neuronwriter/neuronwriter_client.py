"""
NeuronWriter API Client
Unofficial Python client for NeuronWriter SEO content optimization platform.

This client was reverse-engineered from app.neuronwriter.com
"""

import requests
from typing import Dict, List, Optional, Any, Union
import json
from urllib.parse import urljoin
import os


class NeuronWriterError(Exception):
    """Base exception for NeuronWriter API errors"""
    pass


class AuthenticationError(NeuronWriterError):
    """Raised when authentication fails"""
    pass


class APIError(NeuronWriterError):
    """Raised when API request fails"""
    pass


class NeuronWriterClient:
    """
    Client for interacting with NeuronWriter API.

    Authentication:
        NeuronWriter uses session-based authentication via cookies.
        The API requires X-API-KEY header for API endpoints.

    Usage:
        >>> client = NeuronWriterClient(
        ...     email="your@email.com",
        ...     password="your_password"
        ... )
        >>> client.login()
        >>> projects = client.get_projects()
    """

    BASE_URL = "https://app.neuronwriter.com"
    API_BASE = "https://app.neuronwriter.com/api"

    def __init__(
        self,
        email: Optional[str] = None,
        password: Optional[str] = None,
        api_key: Optional[str] = None,
        session: Optional[requests.Session] = None
    ):
        """
        Initialize NeuronWriter client.

        Args:
            email: Account email address
            password: Account password
            api_key: API key for authenticated requests (required for API endpoints)
            session: Optional requests.Session object for reusing connections
        """
        self.email = email or os.environ.get("NEURONWRITER_EMAIL")
        self.password = password or os.environ.get("NEURONWRITER_PASSWORD")
        self.api_key = api_key or os.environ.get("NEURONWRITER_API_KEY")

        self.session = session or requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36",
            "Accept": "application/json, text/html",
            "Accept-Language": "en-US,en;q=0.9",
        })

        self.authenticated = False

    def _make_request(
        self,
        method: str,
        endpoint: str,
        data: Optional[Dict] = None,
        json_data: Optional[Dict] = None,
        params: Optional[Dict] = None,
        use_api: bool = False,
        **kwargs
    ) -> Union[Dict, str]:
        """
        Make HTTP request to NeuronWriter.

        Args:
            method: HTTP method (GET, POST, etc.)
            endpoint: API endpoint path
            data: Form data for POST requests
            json_data: JSON data for POST requests
            params: URL parameters
            use_api: Whether to use API base URL and add X-API-KEY header
            **kwargs: Additional arguments passed to requests

        Returns:
            Response data (JSON dict or text)

        Raises:
            APIError: If request fails
        """
        base_url = self.API_BASE if use_api else self.BASE_URL
        url = urljoin(base_url, endpoint.lstrip('/'))

        headers = kwargs.pop('headers', {})
        if use_api and self.api_key:
            headers['X-API-KEY'] = self.api_key

        if json_data:
            headers['Content-Type'] = 'application/json'

        try:
            response = self.session.request(
                method=method,
                url=url,
                data=data,
                json=json_data,
                params=params,
                headers=headers,
                timeout=30,
                **kwargs
            )

            # Try to parse as JSON first
            try:
                return response.json()
            except json.JSONDecodeError:
                # Return text for non-JSON responses
                return response.text

        except requests.RequestException as e:
            raise APIError(f"Request failed: {str(e)}")

    def login(self) -> bool:
        """
        Authenticate with NeuronWriter using email and password.

        This performs a traditional form-based login and establishes
        a session cookie (contai_session_id).

        Returns:
            True if login successful

        Raises:
            AuthenticationError: If login fails
            ValueError: If email or password not provided
        """
        if not self.email or not self.password:
            raise ValueError("Email and password are required for login")

        # First, get the login page to establish session
        try:
            self.session.get(f"{self.BASE_URL}/")
        except requests.RequestException as e:
            raise AuthenticationError(f"Failed to access login page: {e}")

        # Submit login form
        login_data = {
            'email': self.email,
            'password': self.password,
            'redirect_url': '/'
        }

        try:
            response = self.session.post(
                f"{self.BASE_URL}/ucp/login",
                data=login_data,
                allow_redirects=True
            )

            # Check if login was successful
            # Successful login should redirect to dashboard or have logout link
            if response.url != f"{self.BASE_URL}/ucp/login":
                self.authenticated = True
                return True

            # Check response content for error messages
            if "don't match" in response.text.lower() or "invalid" in response.text.lower():
                raise AuthenticationError("Invalid email or password")

            # If we're still on login page, authentication failed
            raise AuthenticationError("Login failed - still on login page")

        except requests.RequestException as e:
            raise AuthenticationError(f"Login request failed: {e}")

    def get_session_info(self) -> Dict[str, Any]:
        """
        Get current session information including cookies and user data.

        Returns:
            Dictionary with session info
        """
        return {
            'cookies': dict(self.session.cookies),
            'authenticated': self.authenticated,
            'email': self.email
        }

    # ===========================================
    # User & Profile Management
    # ===========================================

    def get_profile(self) -> Dict[str, Any]:
        """Get user profile information."""
        return self._make_request('GET', '/ucp/profile')

    def update_preference(self, preference_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Update user preferences.

        Args:
            preference_data: Dictionary of preferences to update

        Returns:
            Updated preference data
        """
        return self._make_request(
            'POST',
            '/ucp/update-preference',
            json_data=preference_data
        )

    # ===========================================
    # Backend/Inventory Management
    # ===========================================

    def add_inventory_urls(self, urls: List[str]) -> Dict[str, Any]:
        """
        Add URLs to inventory for tracking/analysis.

        Args:
            urls: List of URLs to add to inventory

        Returns:
            Response with added URL info
        """
        return self._make_request(
            'POST',
            '/backend/add-inventory-urls',
            json_data={'urls': urls}
        )

    def add_inventory_keywords(self, keywords: List[str]) -> Dict[str, Any]:
        """
        Add keywords to inventory for tracking.

        Args:
            keywords: List of keywords to track

        Returns:
            Response with added keyword info
        """
        return self._make_request(
            'POST',
            '/backend/add-inventory-keywords',
            json_data={'keywords': keywords}
        )

    def request_moz_update(self, url: str) -> Dict[str, Any]:
        """
        Request MOZ metrics update for a URL.

        Args:
            url: URL to update MOZ metrics for

        Returns:
            Response with update status
        """
        return self._make_request(
            'POST',
            '/backend/request-moz-update',
            json_data={'url': url}
        )

    def request_volume_update(self, keyword: str) -> Dict[str, Any]:
        """
        Request search volume update for a keyword.

        Args:
            keyword: Keyword to update volume for

        Returns:
            Response with update status
        """
        return self._make_request(
            'POST',
            '/backend/request-volume-update',
            json_data={'keyword': keyword}
        )

    def export_table(
        self,
        dt_id: str,
        ajax_table: bool = False,
        extra: Optional[Dict] = None
    ) -> bytes:
        """
        Export data table to file format (XLS/CSV).

        Args:
            dt_id: DataTable ID to export
            ajax_table: Whether this is an AJAX-loaded table
            extra: Extra parameters for export

        Returns:
            File content as bytes
        """
        data = {
            'dt_id': dt_id,
            'ajax_table': ajax_table
        }
        if extra:
            data['extra'] = json.dumps(extra)

        response = self.session.post(
            f"{self.BASE_URL}/backend/export-table",
            data=data
        )
        return response.content

    # ===========================================
    # API Endpoints (require X-API-KEY header)
    # ===========================================

    def api_login(self) -> Dict[str, Any]:
        """
        Login via API endpoint (requires X-API-KEY header).

        This is an alternative to form-based login for API access.

        Returns:
            API response with auth token

        Raises:
            AuthenticationError: If API key is missing or login fails
        """
        if not self.api_key:
            raise AuthenticationError("API key is required for API login")

        if not self.email or not self.password:
            raise ValueError("Email and password are required")

        return self._make_request(
            'POST',
            '/login',
            json_data={
                'email': self.email,
                'password': self.password
            },
            use_api=True
        )

    # ===========================================
    # Projects & Documents
    # (These endpoints need to be discovered through actual usage)
    # ===========================================

    def get_projects(self, **params) -> List[Dict[str, Any]]:
        """
        Get list of projects.

        Note: Exact endpoint needs verification with valid credentials.
        Common patterns: /projects, /api/projects, /backend/projects

        Returns:
            List of projects
        """
        # Try multiple possible endpoints
        for endpoint in ['/api/projects', '/projects', '/backend/projects']:
            try:
                result = self._make_request('GET', endpoint, params=params, use_api=True)
                return result if isinstance(result, list) else result.get('projects', [])
            except:
                continue

        raise APIError("Unable to fetch projects - endpoint not found")

    def create_project(self, name: str, **kwargs) -> Dict[str, Any]:
        """
        Create a new project.

        Args:
            name: Project name
            **kwargs: Additional project parameters

        Returns:
            Created project data
        """
        data = {'name': name, **kwargs}
        return self._make_request('POST', '/api/projects', json_data=data, use_api=True)

    def get_documents(self, project_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Get list of documents, optionally filtered by project.

        Args:
            project_id: Optional project ID to filter documents

        Returns:
            List of documents
        """
        params = {}
        if project_id:
            params['project_id'] = project_id

        return self._make_request('GET', '/api/documents', params=params, use_api=True)

    def create_document(
        self,
        title: str,
        project_id: Optional[str] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Create a new document.

        Args:
            title: Document title
            project_id: Optional project ID
            **kwargs: Additional document parameters

        Returns:
            Created document data
        """
        data = {'title': title, **kwargs}
        if project_id:
            data['project_id'] = project_id

        return self._make_request('POST', '/api/documents', json_data=data, use_api=True)

    def get_document(self, document_id: str) -> Dict[str, Any]:
        """
        Get document details.

        Args:
            document_id: Document ID

        Returns:
            Document data
        """
        return self._make_request('GET', f'/api/documents/{document_id}', use_api=True)

    def update_document(self, document_id: str, **kwargs) -> Dict[str, Any]:
        """
        Update document.

        Args:
            document_id: Document ID
            **kwargs: Fields to update

        Returns:
            Updated document data
        """
        return self._make_request(
            'PUT',
            f'/api/documents/{document_id}',
            json_data=kwargs,
            use_api=True
        )

    def delete_document(self, document_id: str) -> Dict[str, Any]:
        """
        Delete document.

        Args:
            document_id: Document ID

        Returns:
            Deletion confirmation
        """
        return self._make_request('DELETE', f'/api/documents/{document_id}', use_api=True)

    # ===========================================
    # Content Analysis & Optimization
    # ===========================================

    def analyze_content(
        self,
        content: str,
        target_keyword: str,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Analyze content for SEO optimization.

        Args:
            content: Content text to analyze
            target_keyword: Target SEO keyword
            **kwargs: Additional analysis parameters

        Returns:
            Analysis results with SEO scores and recommendations
        """
        data = {
            'content': content,
            'keyword': target_keyword,
            **kwargs
        }
        return self._make_request('POST', '/api/analyze', json_data=data, use_api=True)

    def get_serp_analysis(
        self,
        keyword: str,
        location: str = 'US',
        language: str = 'en'
    ) -> Dict[str, Any]:
        """
        Get SERP (Search Engine Results Page) analysis for keyword.

        Args:
            keyword: Keyword to analyze
            location: Location code for search results
            language: Language code

        Returns:
            SERP analysis data
        """
        params = {
            'keyword': keyword,
            'location': location,
            'language': language
        }
        return self._make_request('GET', '/api/serp', params=params, use_api=True)

    def get_nlp_terms(self, keyword: str) -> Dict[str, Any]:
        """
        Get NLP terms and recommendations for keyword.

        Args:
            keyword: Target keyword

        Returns:
            NLP terms and usage recommendations
        """
        return self._make_request(
            'GET',
            '/api/nlp-terms',
            params={'keyword': keyword},
            use_api=True
        )

    def get_competitor_analysis(
        self,
        keyword: str,
        competitor_urls: List[str]
    ) -> Dict[str, Any]:
        """
        Analyze competitor content for keyword.

        Args:
            keyword: Target keyword
            competitor_urls: List of competitor URLs to analyze

        Returns:
            Competitor analysis data
        """
        data = {
            'keyword': keyword,
            'competitors': competitor_urls
        }
        return self._make_request('POST', '/api/competitors', json_data=data, use_api=True)

    # ===========================================
    # Templates
    # ===========================================

    def get_templates(self) -> List[Dict[str, Any]]:
        """
        Get list of content templates.

        Returns:
            List of templates
        """
        return self._make_request('GET', '/api/templates', use_api=True)

    def create_template(self, name: str, content: str, **kwargs) -> Dict[str, Any]:
        """
        Create a new content template.

        Args:
            name: Template name
            content: Template content
            **kwargs: Additional template parameters

        Returns:
            Created template data
        """
        data = {'name': name, 'content': content, **kwargs}
        return self._make_request('POST', '/api/templates', json_data=data, use_api=True)

    # ===========================================
    # Utility Methods
    # ===========================================

    def logout(self) -> None:
        """Logout and clear session."""
        try:
            self.session.get(f"{self.BASE_URL}/ucp/logout")
        except:
            pass
        finally:
            self.authenticated = False
            self.session.cookies.clear()

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - cleanup session."""
        self.logout()

    def __repr__(self) -> str:
        return f"<NeuronWriterClient authenticated={self.authenticated} email={self.email}>"


def main():
    """Example usage"""
    import sys

    # Get credentials from environment variables
    email = os.environ.get("NEURONWRITER_EMAIL")
    password = os.environ.get("NEURONWRITER_PASSWORD")
    api_key = os.environ.get("NEURONWRITER_API_KEY")

    if not email or not password:
        print("Error: NEURONWRITER_EMAIL and NEURONWRITER_PASSWORD environment variables required")
        sys.exit(1)

    print("NeuronWriter API Client - Test Script")
    print("=" * 50)

    try:
        # Initialize client
        print(f"\n1. Initializing client for {email}...")
        client = NeuronWriterClient(email=email, password=password, api_key=api_key)

        # Login
        print("\n2. Logging in...")
        client.login()
        print("   ✓ Login successful!")

        # Get session info
        print("\n3. Session info:")
        session_info = client.get_session_info()
        print(f"   Authenticated: {session_info['authenticated']}")
        print(f"   Cookies: {list(session_info['cookies'].keys())}")

        # Try to get profile
        print("\n4. Fetching profile...")
        try:
            profile = client.get_profile()
            print(f"   Profile data: {profile}")
        except Exception as e:
            print(f"   Note: Profile fetch failed (may need valid login): {e}")

        # Try inventory methods
        print("\n5. Testing inventory methods...")
        try:
            # These will fail without valid login, but demonstrate usage
            result = client.add_inventory_urls(['https://example.com'])
            print(f"   Added URLs: {result}")
        except Exception as e:
            print(f"   Note: Inventory test failed (expected without valid auth): {e}")

        print("\n" + "=" * 50)
        print("Test completed! See above for results.")
        print("\nNote: Many endpoints require valid authentication to work properly.")
        print("Update your credentials and try again if authentication failed.")

    except AuthenticationError as e:
        print(f"\n✗ Authentication failed: {e}")
        print("\nPlease verify your credentials:")
        print(f"  Email: {email}")
        print("  Password: [hidden]")
        sys.exit(1)
    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
