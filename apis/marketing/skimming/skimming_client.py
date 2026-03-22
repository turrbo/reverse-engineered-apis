#!/usr/bin/env python3
"""
Skimming AI / NEURONwriter API Client

Note: During testing, app.skimming.ai redirects to app.neuronwriter.com
The provided credentials did not authenticate successfully.
This client template is based on observed network traffic patterns.
"""

import os
import requests
from typing import Optional, Dict, Any
import json


class SkimmingClient:
    """
    Client for interacting with Skimming AI / NEURONwriter API

    Note: Domain app.skimming.ai redirects to app.neuronwriter.com
    """

    def __init__(self, email: Optional[str] = None, password: Optional[str] = None):
        """
        Initialize the Skimming AI client

        Args:
            email: User email address (or set SKIMMING_EMAIL env var)
            password: User password (or set SKIMMING_PASSWORD env var)
        """
        self.email = email or os.getenv('SKIMMING_EMAIL')
        self.password = password or os.getenv('SKIMMING_PASSWORD')

        if not self.email or not self.password:
            raise ValueError(
                "Email and password are required. "
                "Provide them as arguments or set SKIMMING_EMAIL and SKIMMING_PASSWORD environment variables."
            )

        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'application/json',
            'Content-Type': 'application/json',
        })

        self.base_url = 'https://app.neuronwriter.com'
        self.access_token: Optional[str] = None
        self.user_data: Optional[Dict[str, Any]] = None

    def login(self) -> Dict[str, Any]:
        """
        Authenticate with the Skimming AI / NEURONwriter API

        Returns:
            dict: Authentication response containing user data and tokens

        Raises:
            requests.HTTPError: If authentication fails
        """
        login_url = f'{self.base_url}/api/login'

        payload = {
            'email': self.email,
            'password': self.password
        }

        response = self.session.post(login_url, json=payload)
        response.raise_for_status()

        data = response.json()

        # Extract and store authentication token
        if 'access_token' in data:
            self.access_token = data['access_token']
            self.session.headers['Authorization'] = f'Bearer {self.access_token}'

        if 'token' in data:
            self.access_token = data['token']
            self.session.headers['Authorization'] = f'Bearer {self.access_token}'

        self.user_data = data.get('user', data)

        return data

    def get_user_profile(self) -> Dict[str, Any]:
        """
        Get the current user's profile information

        Returns:
            dict: User profile data
        """
        if not self.access_token:
            raise RuntimeError("Not authenticated. Call login() first.")

        url = f'{self.base_url}/api/user/profile'
        response = self.session.get(url)
        response.raise_for_status()
        return response.json()

    def get_documents(self) -> Dict[str, Any]:
        """
        Get list of user's documents

        Returns:
            dict: List of documents
        """
        if not self.access_token:
            raise RuntimeError("Not authenticated. Call login() first.")

        url = f'{self.base_url}/api/documents'
        response = self.session.get(url)
        response.raise_for_status()
        return response.json()

    def create_document(self, title: str, content: str = '') -> Dict[str, Any]:
        """
        Create a new document

        Args:
            title: Document title
            content: Initial document content

        Returns:
            dict: Created document data
        """
        if not self.access_token:
            raise RuntimeError("Not authenticated. Call login() first.")

        url = f'{self.base_url}/api/documents'
        payload = {
            'title': title,
            'content': content
        }

        response = self.session.post(url, json=payload)
        response.raise_for_status()
        return response.json()

    def get_document(self, document_id: str) -> Dict[str, Any]:
        """
        Get a specific document by ID

        Args:
            document_id: Document identifier

        Returns:
            dict: Document data
        """
        if not self.access_token:
            raise RuntimeError("Not authenticated. Call login() first.")

        url = f'{self.base_url}/api/documents/{document_id}'
        response = self.session.get(url)
        response.raise_for_status()
        return response.json()

    def summarize_text(self, text: str, **options) -> Dict[str, Any]:
        """
        Summarize provided text

        Args:
            text: Text to summarize
            **options: Additional summarization options

        Returns:
            dict: Summarization result
        """
        if not self.access_token:
            raise RuntimeError("Not authenticated. Call login() first.")

        url = f'{self.base_url}/api/summarize'
        payload = {
            'text': text,
            **options
        }

        response = self.session.post(url, json=payload)
        response.raise_for_status()
        return response.json()

    def analyze_url(self, url: str) -> Dict[str, Any]:
        """
        Analyze content from a URL

        Args:
            url: URL to analyze

        Returns:
            dict: Analysis result
        """
        if not self.access_token:
            raise RuntimeError("Not authenticated. Call login() first.")

        api_url = f'{self.base_url}/api/analyze'
        payload = {
            'url': url
        }

        response = self.session.post(api_url, json=payload)
        response.raise_for_status()
        return response.json()


def main():
    """
    Example usage of the Skimming AI client

    Set environment variables:
        export SKIMMING_EMAIL="your-email@example.com"
        export SKIMMING_PASSWORD="your-password"
    """
    try:
        # Initialize client
        client = SkimmingClient()
        print("Skimming AI Client initialized")

        # Login
        print("\nAttempting login...")
        auth_response = client.login()
        print(f"Login successful!")
        print(f"User: {json.dumps(client.user_data, indent=2)}")

        # Get user profile
        print("\nFetching user profile...")
        profile = client.get_user_profile()
        print(f"Profile: {json.dumps(profile, indent=2)}")

        # Get documents
        print("\nFetching documents...")
        documents = client.get_documents()
        print(f"Documents: {json.dumps(documents, indent=2)}")

    except ValueError as e:
        print(f"Configuration error: {e}")
        print("\nPlease set environment variables:")
        print("  export SKIMMING_EMAIL='your-email@example.com'")
        print("  export SKIMMING_PASSWORD='your-password'")
    except requests.HTTPError as e:
        print(f"API error: {e}")
        print(f"Response: {e.response.text if e.response else 'No response'}")
    except Exception as e:
        print(f"Unexpected error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == '__main__':
    main()
