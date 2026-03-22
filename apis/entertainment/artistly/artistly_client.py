#!/usr/bin/env python3
"""
Artistly AI API Client
A Python client for interacting with the Artistly.ai image generation platform.

This client handles authentication and provides methods to generate AI images
using various styles and tools available on the Artistly.ai platform.

Author: Reverse engineered from app.artistly.ai
Date: 2026-03-22
"""

import requests
import json
import time
from typing import Optional, Dict, List, Any
from urllib.parse import unquote
import re
import html as html_module


class ArtistlyClient:
    """
    Client for interacting with Artistly.ai API.

    Authentication uses email/password login with session cookies and CSRF tokens.
    The platform uses Laravel with Inertia.js for its backend.
    """

    def __init__(self, email: str, password: str):
        """
        Initialize the Artistly client.

        Args:
            email: User's email address
            password: User's password
        """
        self.email = email
        self.password = password
        self.session = requests.Session()
        self.base_url = "https://app.artistly.ai"
        self.authenticated = False
        self.user_info: Optional[Dict[str, Any]] = None

        # Default headers
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "en-US,en;q=0.9",
        }

    def login(self) -> bool:
        """
        Authenticate with Artistly.ai using email and password.

        The login flow:
        1. GET /login to obtain XSRF-TOKEN cookie
        2. POST /login with email, password, and XSRF token
        3. Session cookies are stored for subsequent requests

        Returns:
            bool: True if login successful, False otherwise
        """
        try:
            # Step 1: Get login page to obtain CSRF token
            login_page = self.session.get(
                f"{self.base_url}/login",
                headers=self.headers
            )

            if login_page.status_code != 200:
                print(f"Failed to access login page: {login_page.status_code}")
                return False

            # Extract XSRF token from cookie
            xsrf_token = unquote(self.session.cookies.get("XSRF-TOKEN", ""))

            if not xsrf_token:
                print("Failed to obtain XSRF token")
                return False

            # Step 2: Perform login
            login_data = {
                "email": self.email,
                "password": self.password,
                "remember": "false"
            }

            login_headers = {
                **self.headers,
                "Content-Type": "application/x-www-form-urlencoded",
                "Origin": self.base_url,
                "Referer": f"{self.base_url}/login",
                "X-XSRF-TOKEN": xsrf_token,
            }

            login_response = self.session.post(
                f"{self.base_url}/login",
                data=login_data,
                headers=login_headers,
                allow_redirects=False
            )

            # Check for redirect (successful login)
            if login_response.status_code in [302, 301]:
                redirect_url = login_response.headers.get("Location", "")

                # Verify we have session cookies
                if "artistly_session" in self.session.cookies:
                    self.authenticated = True

                    # Fetch user info
                    self._fetch_user_info()

                    print(f"✓ Login successful! Redirected to: {redirect_url}")
                    if self.user_info:
                        print(f"  Logged in as: {self.user_info.get('name')} ({self.user_info.get('email')})")

                    return True
                else:
                    print("Login redirect received but no session cookie found")
                    return False
            else:
                print(f"Login failed with status: {login_response.status_code}")
                try:
                    error = login_response.json()
                    print(f"  Error: {error}")
                except:
                    pass
                return False

        except Exception as e:
            print(f"Login error: {e}")
            return False

    def _fetch_user_info(self):
        """Fetch user information from the dashboard."""
        try:
            dashboard = self.session.get(
                f"{self.base_url}/dashboard",
                headers=self.headers
            )

            if dashboard.status_code == 200:
                # Extract Inertia.js page data
                pattern = r'<div id="app" data-page="([^"]+)"'
                match = re.search(pattern, dashboard.text)
                if match:
                    page_data = html_module.unescape(match.group(1))
                    data = json.loads(page_data)

                    if 'props' in data and 'auth' in data['props']:
                        self.user_info = data['props']['auth'].get('user')
        except:
            pass

    def _get_xsrf_token(self) -> str:
        """Get current XSRF token from cookies."""
        return unquote(self.session.cookies.get("XSRF-TOKEN", ""))

    def _make_request(
        self,
        method: str,
        endpoint: str,
        data: Optional[Dict] = None,
        json_data: Optional[Dict] = None,
        referer: Optional[str] = None
    ) -> requests.Response:
        """
        Make an authenticated API request.

        Args:
            method: HTTP method (GET, POST, PUT, DELETE)
            endpoint: API endpoint (e.g., /tshirt-images)
            data: Form data for POST requests
            json_data: JSON data for POST requests
            referer: Referer header value

        Returns:
            requests.Response object
        """
        if not self.authenticated:
            raise Exception("Not authenticated. Call login() first.")

        url = f"{self.base_url}{endpoint}"

        request_headers = {
            **self.headers,
            "X-XSRF-TOKEN": self._get_xsrf_token(),
            "X-Requested-With": "XMLHttpRequest",
            "Origin": self.base_url,
        }

        if referer:
            request_headers["Referer"] = referer

        if json_data:
            request_headers["Content-Type"] = "application/json"

        if method == "GET":
            return self.session.get(url, headers=request_headers)
        elif method == "POST":
            if json_data:
                return self.session.post(url, json=json_data, headers=request_headers)
            else:
                return self.session.post(url, data=data, headers=request_headers)
        elif method == "PUT":
            return self.session.put(url, json=json_data, headers=request_headers)
        elif method == "DELETE":
            return self.session.delete(url, headers=request_headers)
        else:
            raise ValueError(f"Unsupported method: {method}")

    def get_illustrator_styles(self) -> List[Dict[str, Any]]:
        """
        Get list of available illustrator styles.

        Returns:
            List of style dictionaries with keys: label, style, cover, prefix, suffix
        """
        try:
            dashboard = self.session.get(
                f"{self.base_url}/dashboard",
                headers=self.headers
            )

            if dashboard.status_code == 200:
                pattern = r'<div id="app" data-page="([^"]+)"'
                match = re.search(pattern, dashboard.text)
                if match:
                    page_data = html_module.unescape(match.group(1))
                    data = json.loads(page_data)

                    if 'props' in data and 'illustratorStyles' in data['props']:
                        return data['props']['illustratorStyles']

            return []
        except Exception as e:
            print(f"Error fetching styles: {e}")
            return []

    def generate_tshirt_images(
        self,
        prompts: List[str],
        style: str = "36",
        additional_params: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """
        Generate T-shirt design images.

        Args:
            prompts: List of text prompts for image generation
            style: Style ID from illustrator styles (default: "36" = 2D Flat)
            additional_params: Additional parameters to pass to the API

        Returns:
            Dictionary with generation response data

        Example:
            >>> client.generate_tshirt_images(
            ...     prompts=["A cute cat wearing sunglasses"],
            ...     style="36"
            ... )
        """
        data = {
            "tshirt_prompts": prompts,
            "style": style,
        }

        if additional_params:
            data.update(additional_params)

        response = self._make_request(
            "POST",
            "/tshirt-images",
            json_data=data,
            referer=f"{self.base_url}/choose-designer"
        )

        return self._parse_inertia_response(response)

    def generate_storybook_images(
        self,
        prompts: List[str],
        style: Optional[str] = None,
        additional_params: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """
        Generate storybook illustration images.

        Args:
            prompts: List of text prompts for image generation
            style: Style ID from illustrator styles (optional)
            additional_params: Additional parameters to pass to the API

        Returns:
            Dictionary with generation response data
        """
        data = {
            "prompts": prompts,
        }

        if style:
            data["style"] = style

        if additional_params:
            data.update(additional_params)

        response = self._make_request(
            "POST",
            "/story-book-images",
            json_data=data,
            referer=f"{self.base_url}/choose-designer"
        )

        return self._parse_inertia_response(response)

    def stylize_image(
        self,
        image_url: str,
        style: Optional[str] = None,
        prompt: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Stylize an existing image.

        Args:
            image_url: URL of the image to stylize
            style: Style to apply
            prompt: Text prompt for stylization

        Returns:
            Dictionary with generation response data
        """
        data = {
            "image_url": image_url,
        }

        if style:
            data["style"] = style
        if prompt:
            data["prompt"] = prompt

        response = self._make_request(
            "POST",
            "/stylize-image",
            json_data=data
        )

        return self._parse_inertia_response(response)

    def get_personal_designs(self) -> Dict[str, Any]:
        """
        Get user's personal designs/generated images.

        Returns:
            Dictionary with user's designs
        """
        response = self._make_request(
            "GET",
            "/fetch-personal-designs"
        )

        try:
            return response.json()
        except:
            return {"error": "Failed to parse response"}

    def get_folders(self) -> List[Dict[str, Any]]:
        """
        Get user's design folders.

        Returns:
            List of folder dictionaries
        """
        try:
            dashboard = self.session.get(
                f"{self.base_url}/dashboard",
                headers=self.headers
            )

            if dashboard.status_code == 200:
                pattern = r'<div id="app" data-page="([^"]+)"'
                match = re.search(pattern, dashboard.text)
                if match:
                    page_data = html_module.unescape(match.group(1))
                    data = json.loads(page_data)

                    if 'props' in data:
                        folders = data['props'].get('personal_folders', [])
                        return folders

            return []
        except Exception as e:
            print(f"Error fetching folders: {e}")
            return []

    def download_design(self, uuid: str, output_path: str) -> bool:
        """
        Download a generated design by UUID.

        Args:
            uuid: Design UUID
            output_path: Local path to save the downloaded file

        Returns:
            bool: True if download successful
        """
        try:
            response = self._make_request(
                "GET",
                f"/{uuid}/download"
            )

            if response.status_code == 200:
                with open(output_path, 'wb') as f:
                    f.write(response.content)
                return True
            else:
                print(f"Download failed: {response.status_code}")
                return False

        except Exception as e:
            print(f"Download error: {e}")
            return False

    def _parse_inertia_response(self, response: requests.Response) -> Dict[str, Any]:
        """
        Parse an Inertia.js HTML response and extract the page data.

        Args:
            response: Response object from an API call

        Returns:
            Dictionary with parsed data or error information
        """
        if response.status_code == 200:
            try:
                # Try to parse as JSON first
                return response.json()
            except:
                # Parse as Inertia HTML response
                pattern = r'<div id="app" data-page="([^"]+)"'
                match = re.search(pattern, response.text)
                if match:
                    page_data = html_module.unescape(match.group(1))
                    data = json.loads(page_data)
                    return {
                        "status": "success",
                        "component": data.get("component"),
                        "message": "Request submitted successfully. Generation started.",
                        "note": "Images are generated asynchronously. Use get_personal_designs() to fetch results."
                    }
                else:
                    return {
                        "status": "unknown",
                        "message": "Received HTML response but could not parse Inertia data"
                    }
        else:
            try:
                error = response.json()
                return {
                    "status": "error",
                    "status_code": response.status_code,
                    "error": error
                }
            except:
                return {
                    "status": "error",
                    "status_code": response.status_code,
                    "message": response.text[:500]
                }


def main():
    """
    Example usage of the Artistly client.

    Set credentials via environment variables:
        export ARTISTLY_EMAIL="your-email@example.com"
        export ARTISTLY_PASSWORD="your-password"
    """
    import os

    # Get credentials from environment variables (NEVER hardcode!)
    email = os.getenv("ARTISTLY_EMAIL")
    password = os.getenv("ARTISTLY_PASSWORD")

    if not email or not password:
        print("Error: Please set ARTISTLY_EMAIL and ARTISTLY_PASSWORD environment variables")
        print("\nExample:")
        print('  export ARTISTLY_EMAIL="your-email@example.com"')
        print('  export ARTISTLY_PASSWORD="your-password"')
        print('  python artistly_client.py')
        return

    # Initialize client
    print("="*60)
    print("Artistly AI API Client Demo")
    print("="*60)

    client = ArtistlyClient(email, password)

    # Login
    print("\n[1] Logging in...")
    if not client.login():
        print("Failed to login. Please check your credentials.")
        return

    # Get available styles
    print("\n[2] Fetching available illustrator styles...")
    styles = client.get_illustrator_styles()
    print(f"Found {len(styles)} styles")
    if styles:
        print("\nFirst 5 styles:")
        for style in styles[:5]:
            print(f"  - {style['label']}: style_id='{style['style']}'")

    # Get folders
    print("\n[3] Fetching user folders...")
    folders = client.get_folders()
    print(f"Found {len(folders)} folders")

    # Generate a T-shirt design
    print("\n[4] Generating T-shirt design...")
    print("Prompt: 'A majestic lion wearing a crown'")
    print("Style: 36 (2D Flat)")

    result = client.generate_tshirt_images(
        prompts=["A majestic lion wearing a crown"],
        style="36"
    )

    print("\nGeneration result:")
    print(json.dumps(result, indent=2))

    # Get personal designs
    print("\n[5] Fetching personal designs...")
    designs = client.get_personal_designs()
    print(f"Response keys: {list(designs.keys())}")

    print("\n" + "="*60)
    print("Demo complete!")
    print("="*60)


if __name__ == "__main__":
    main()
