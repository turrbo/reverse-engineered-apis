#!/usr/bin/env python3
"""
Sociamonials API Client
A Python client for interacting with the Sociamonials.com API (unofficial/reverse-engineered).

This client provides methods to interact with the Sociamonials social media management platform.
Authentication is handled via session cookies after login.
"""

import os
import json
import base64
from typing import Dict, List, Optional, Any
from urllib.parse import urlencode
import requests


class SociamonialAPI:
    """
    Client for interacting with the Sociamonials.com API.

    This is an unofficial client built through reverse engineering the web application.
    Authentication uses session-based cookies (PHPSESSID).
    """

    def __init__(self, username: str, password: str, base_url: str = "https://www.sociamonials.com"):
        """
        Initialize the Sociamonials API client.

        Args:
            username: Sociamonials username
            password: Sociamonials password
            base_url: Base URL for the Sociamonials platform (default: https://www.sociamonials.com)
        """
        self.username = username
        self.password = password
        self.base_url = base_url.rstrip('/')
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'application/json, text/javascript, */*; q=0.01',
            'Accept-Language': 'en-US,en;q=0.9',
            'X-Requested-With': 'XMLHttpRequest',
            'Referer': f'{self.base_url}/accounts/social_media.php'
        })
        self.user_id: Optional[str] = None
        self.user_hash: Optional[str] = None
        self.is_authenticated = False

    def login(self) -> Dict[str, Any]:
        """
        Authenticate with Sociamonials using username and password.

        The login process:
        1. POST to login.php with username/password
        2. Response redirects to password.php which returns JSON with session info
        3. Extracts user_id, user_hash, and session cookies

        Returns:
            Dict containing login response data including user_id, user_hash, and login_status

        Raises:
            requests.exceptions.RequestException: If login request fails
            ValueError: If login credentials are invalid
        """
        login_url = f"{self.base_url}/login.php"

        # First request to get the login page (for any CSRF tokens if needed)
        self.session.get(login_url)

        # Submit login form
        login_data = {
            'username': self.username,
            'password': self.password,
            'remember': '1'
        }

        # The form posts to password.php
        password_url = f"{self.base_url}/password.php"
        response = self.session.post(password_url, data=login_data, allow_redirects=True)

        # Try to parse JSON response
        try:
            result = response.json()

            # Response can be a list or dict - handle both
            if isinstance(result, list) and len(result) > 0:
                result = result[0]  # Take first element if it's a list

            # Check if login was successful
            if isinstance(result, dict):
                if result.get('res_status') == 'success' and result.get('login_status') == '1':
                    self.user_id = result.get('user_id')
                    self.user_hash = result.get('user_hash')
                    self.is_authenticated = True
                    print(f"✓ Login successful! User ID: {self.user_id}")
                    return result
                else:
                    raise ValueError(f"Login failed: {result.get('error_msg', 'Unknown error')}")
            else:
                raise ValueError(f"Login failed: Unexpected response format: {type(result)}")

        except json.JSONDecodeError:
            # If not JSON, check if we have session cookie
            if 'PHPSESSID' in self.session.cookies:
                # Try to access the dashboard to verify authentication
                dashboard_response = self.session.get(f"{self.base_url}/accounts/social_media.php")
                if dashboard_response.status_code == 200 and 'Social Media Dashboard' in dashboard_response.text:
                    self.is_authenticated = True
                    print("✓ Login successful (verified via dashboard access)")
                    return {'status': 'success', 'message': 'Authenticated'}

            raise ValueError("Login failed: Invalid response format")

    def _ensure_authenticated(self):
        """Ensure the client is authenticated before making API calls."""
        if not self.is_authenticated:
            raise RuntimeError("Not authenticated. Call login() first.")

    def extend_session(self) -> Dict[str, Any]:
        """
        Extend the current session (heartbeat endpoint).

        Returns:
            Response from the session extension endpoint
        """
        self._ensure_authenticated()

        url = f"{self.base_url}/accounts/get_heartbit.php"
        data = {'extend_session': '1'}

        response = self.session.post(url, data=data)
        response.raise_for_status()

        try:
            return response.json()
        except json.JSONDecodeError:
            return {'status': 'success', 'text': response.text}

    def get_posts(self,
                  page_name: str = 'pending_posts',
                  status: int = 3,
                  search_type: str = 'message',
                  start: int = 0,
                  length: int = 10,
                  search_value: str = '') -> Dict[str, Any]:
        """
        Get posts from Sociamonials (queue, sent, drafts, etc.).

        Args:
            page_name: Type of posts to retrieve (e.g., 'pending_posts', 'published_posts', 'draft_posts')
            status: Post status code (3 = pending/queue)
            search_type: Type of search ('message', 'date', etc.)
            start: Pagination start offset
            length: Number of records to retrieve
            search_value: Optional search query

        Returns:
            DataTables-formatted JSON response with posts data
        """
        self._ensure_authenticated()

        url = f"{self.base_url}/accounts/grid_data.php"
        params = {
            'pageName': page_name,
            'status': status,
            'search_type': search_type,
            'sm_timeformat_id': '1'
        }

        # DataTables parameters
        dt_params = {
            'draw': '1',
            'start': start,
            'length': length,
            'search[value]': search_value,
            'search[regex]': 'false'
        }

        # Add column definitions (DataTables format)
        for i in range(8):
            dt_params[f'columns[{i}][data]'] = str(i)
            dt_params[f'columns[{i}][name]'] = ''
            dt_params[f'columns[{i}][searchable]'] = 'true'
            dt_params[f'columns[{i}][orderable]'] = 'true' if i == 7 else 'false'
            dt_params[f'columns[{i}][search][value]'] = ''
            dt_params[f'columns[{i}][search][regex]'] = 'false'

        # Ordering
        dt_params['order[0][column]'] = '7'
        dt_params['order[0][dir]'] = 'desc'

        full_url = f"{url}?{urlencode(params)}"
        response = self.session.post(full_url, data=dt_params)
        response.raise_for_status()

        # Handle empty or non-JSON responses
        try:
            return response.json()
        except json.JSONDecodeError:
            # Return empty DataTables response format if JSON parsing fails
            return {
                'draw': 1,
                'recordsTotal': 0,
                'recordsFiltered': 0,
                'data': [],
                'error': f'Invalid JSON response: {response.text[:200]}'
            }

    def get_queued_posts(self, start: int = 0, length: int = 10) -> Dict[str, Any]:
        """
        Get posts in the queue (pending/scheduled posts).

        Args:
            start: Pagination offset
            length: Number of records

        Returns:
            List of queued posts
        """
        return self.get_posts(page_name='pending_posts', status=3, start=start, length=length)

    def get_sent_posts(self, start: int = 0, length: int = 10) -> Dict[str, Any]:
        """
        Get published/sent posts.

        Args:
            start: Pagination offset
            length: Number of records

        Returns:
            List of sent posts
        """
        return self.get_posts(page_name='published_posts', status=1, start=start, length=length)

    def get_draft_posts(self, start: int = 0, length: int = 10) -> Dict[str, Any]:
        """
        Get draft posts.

        Args:
            start: Pagination offset
            length: Number of records

        Returns:
            List of draft posts
        """
        return self.get_posts(page_name='draft_posts', status=2, start=start, length=length)

    def get_calendar_data(self) -> str:
        """
        Get calendar view data.

        Returns:
            Calendar page HTML/data
        """
        self._ensure_authenticated()

        url = f"{self.base_url}/accounts/calendar.php"
        response = self.session.get(url)
        response.raise_for_status()

        return response.text

    def get_reports(self) -> str:
        """
        Get social media reports/analytics.

        Returns:
            Reports page HTML/data
        """
        self._ensure_authenticated()

        url = f"{self.base_url}/accounts/socialmedia_report.php"
        response = self.session.get(url)
        response.raise_for_status()

        return response.text

    def get_campaigns(self) -> str:
        """
        Get campaigns/social tiles.

        Returns:
            Campaigns page HTML/data
        """
        self._ensure_authenticated()

        url = f"{self.base_url}/accounts/manage_socialtiles.php"
        response = self.session.get(url)
        response.raise_for_status()

        return response.text

    def get_social_crm(self) -> str:
        """
        Get Social CRM database.

        Returns:
            Social CRM page HTML/data
        """
        self._ensure_authenticated()

        url = f"{self.base_url}/accounts/socialcrm_database.php"
        response = self.session.get(url)
        response.raise_for_status()

        return response.text

    def get_ai_writer(self) -> str:
        """
        Get AI Writer page.

        Returns:
            AI Writer page HTML/data
        """
        self._ensure_authenticated()

        url = f"{self.base_url}/accounts/ai_writer.php"
        response = self.session.get(url)
        response.raise_for_status()

        return response.text

    def get_account_settings(self) -> str:
        """
        Get account settings.

        Returns:
            Account settings page HTML/data
        """
        self._ensure_authenticated()

        url = f"{self.base_url}/accounts/account_settings.php"
        response = self.session.get(url)
        response.raise_for_status()

        return response.text

    def get_integrations(self) -> str:
        """
        Get account integrations page.

        Returns:
            Integrations page HTML/data
        """
        self._ensure_authenticated()

        url = f"{self.base_url}/accounts/account_integrations.php"
        response = self.session.get(url)
        response.raise_for_status()

        return response.text

    def logout(self) -> bool:
        """
        Log out from Sociamonials.

        Returns:
            True if logout was successful
        """
        if not self.is_authenticated:
            return True

        try:
            url = f"{self.base_url}/logout.php"
            response = self.session.get(url)
            response.raise_for_status()

            self.is_authenticated = False
            self.user_id = None
            self.user_hash = None
            print("✓ Logged out successfully")
            return True
        except Exception as e:
            print(f"⚠ Logout failed: {e}")
            return False


def main():
    """
    Example usage of the Sociamonials API client.

    Credentials should be provided via environment variables:
    - SOCIAMONIALS_USERNAME
    - SOCIAMONIALS_PASSWORD
    """
    # Get credentials from environment variables
    username = os.getenv('SOCIAMONIALS_USERNAME')
    password = os.getenv('SOCIAMONIALS_PASSWORD')

    if not username or not password:
        print("Error: Please set SOCIAMONIALS_USERNAME and SOCIAMONIALS_PASSWORD environment variables")
        print("\nExample:")
        print('  export SOCIAMONIALS_USERNAME="your_username"')
        print('  export SOCIAMONIALS_PASSWORD="your_password"')
        print('  python sociamonials_client.py')
        return

    # Initialize client
    print("Initializing Sociamonials API client...")
    client = SociamonialAPI(username=username, password=password)

    try:
        # Login
        print("\n1. Authenticating...")
        login_result = client.login()
        print(f"   User ID: {client.user_id}")

        # Extend session (heartbeat)
        print("\n2. Extending session (heartbeat)...")
        heartbeat = client.extend_session()
        print(f"   Heartbeat response: {heartbeat}")

        # Get queued posts
        print("\n3. Fetching queued posts...")
        queued_posts = client.get_queued_posts(length=5)
        print(f"   Total queued posts: {queued_posts.get('recordsTotal', 0)}")
        print(f"   Fetched: {len(queued_posts.get('data', []))} posts")

        # Get sent posts
        print("\n4. Fetching sent posts...")
        sent_posts = client.get_sent_posts(length=5)
        print(f"   Total sent posts: {sent_posts.get('recordsTotal', 0)}")
        print(f"   Fetched: {len(sent_posts.get('data', []))} posts")

        # Get draft posts
        print("\n5. Fetching draft posts...")
        draft_posts = client.get_draft_posts(length=5)
        print(f"   Total draft posts: {draft_posts.get('recordsTotal', 0)}")
        print(f"   Fetched: {len(draft_posts.get('data', []))} posts")

        # Get calendar data
        print("\n6. Fetching calendar data...")
        calendar_html = client.get_calendar_data()
        print(f"   Calendar page size: {len(calendar_html)} bytes")

        # Get reports
        print("\n7. Fetching reports...")
        reports_html = client.get_reports()
        print(f"   Reports page size: {len(reports_html)} bytes")

        print("\n✅ All API calls successful!")

    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()

    finally:
        # Logout
        print("\n8. Logging out...")
        client.logout()


if __name__ == '__main__':
    main()
