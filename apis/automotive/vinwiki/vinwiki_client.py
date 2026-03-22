#!/usr/bin/env python3
"""
VinWiki API Client
A Python client for the undocumented VinWiki REST API.
"""

import os
import sys
from typing import Optional, Dict, Any, List
import requests
from datetime import datetime


class VinWikiClient:
    """Client for interacting with the VinWiki API."""

    BASE_URL = "https://rest.vinwiki.com"

    def __init__(self, email: str, password: str):
        """
        Initialize the VinWiki client.

        Args:
            email: User's email address for authentication
            password: User's password for authentication
        """
        self.email = email
        self.password = password
        self.session = requests.Session()
        self.token: Optional[str] = None
        self.user_uuid: Optional[str] = None
        self.username: Optional[str] = None

    def login(self) -> Dict[str, Any]:
        """
        Authenticate with VinWiki and obtain session token.

        Returns:
            Dict containing authentication response

        Raises:
            requests.HTTPError: If authentication fails
        """
        url = f"{self.BASE_URL}/auth/authenticate"
        payload = {
            "login": self.email,
            "password": self.password
        }

        response = self.session.post(url, json=payload)
        response.raise_for_status()

        # Extract token from Set-Cookie header or localStorage simulation
        # The API returns the token via cookie, but we need to check response
        cookies = response.cookies.get_dict()

        # Make a follow-up request to get user info which will give us the token
        # In the browser, the token is stored in localStorage after login
        # We need to simulate this by making a request that would trigger it

        # Try to get notification count which requires auth
        notif_response = self.session.get(f"{self.BASE_URL}/person/notification_count/me")

        if notif_response.status_code == 200:
            # If this works, we're authenticated via cookie
            # Now we need to extract user info
            # The token is typically returned in a specific way
            # For now, we'll work with cookies
            print("Login successful!")
            return {"status": "ok", "message": "Authenticated via session cookie"}
        else:
            raise Exception("Authentication failed")

    def set_token(self, token: str, user_uuid: Optional[str] = None) -> None:
        """
        Manually set the authentication token.

        Args:
            token: The session token from VinWiki
            user_uuid: Optional user UUID
        """
        self.token = token
        self.user_uuid = user_uuid
        self.session.headers.update({
            "Authorization": token
        })

    def get_notification_count(self) -> Dict[str, Any]:
        """
        Get the current user's notification count.

        Returns:
            Dict containing notification count information
        """
        url = f"{self.BASE_URL}/person/notification_count/me"
        response = self.session.get(url)
        response.raise_for_status()
        return response.json()

    def get_user_feed(self, user_uuid: Optional[str] = None) -> Dict[str, Any]:
        """
        Get the feed for a specific user.

        Args:
            user_uuid: User UUID (uses authenticated user if not provided)

        Returns:
            Dict containing user's feed posts
        """
        uuid = user_uuid or self.user_uuid
        if not uuid:
            raise ValueError("user_uuid must be provided or user must be logged in")

        url = f"{self.BASE_URL}/person/feed/{uuid}"
        response = self.session.get(url)
        response.raise_for_status()
        return response.json()

    def get_recent_vins(self) -> Dict[str, Any]:
        """
        Get recently viewed VINs for the authenticated user.

        Returns:
            Dict containing list of recent vehicles
        """
        url = f"{self.BASE_URL}/person/recent_vins"
        response = self.session.get(url)
        response.raise_for_status()
        return response.json()

    def get_user_profile(self, user_uuid: str) -> Dict[str, Any]:
        """
        Get profile information for a specific user.

        Args:
            user_uuid: The UUID of the user

        Returns:
            Dict containing user profile information
        """
        url = f"{self.BASE_URL}/person/profile/{user_uuid}"
        response = self.session.get(url)
        response.raise_for_status()
        return response.json()

    def get_user_profile_picture(self, user_uuid: str) -> bytes:
        """
        Get profile picture for a specific user.

        Args:
            user_uuid: The UUID of the user

        Returns:
            Raw image bytes
        """
        url = f"{self.BASE_URL}/person/profile_picture/{user_uuid}"
        response = self.session.get(url)
        response.raise_for_status()
        return response.content

    def get_vehicle_by_vin(self, vin: str) -> Dict[str, Any]:
        """
        Get vehicle information by VIN.

        Args:
            vin: The Vehicle Identification Number

        Returns:
            Dict containing vehicle information
        """
        url = f"{self.BASE_URL}/vehicle/vin/{vin}"
        response = self.session.get(url)
        response.raise_for_status()
        return response.json()

    def get_vehicle_feed(self, vin: str) -> Dict[str, Any]:
        """
        Get the post feed for a specific vehicle.

        Args:
            vin: The Vehicle Identification Number

        Returns:
            Dict containing vehicle's post feed
        """
        url = f"{self.BASE_URL}/vehicle/feed/{vin}"
        response = self.session.get(url)
        response.raise_for_status()
        return response.json()

    def is_following_vehicle(self, vin: str) -> Dict[str, Any]:
        """
        Check if the authenticated user is following a vehicle.

        Args:
            vin: The Vehicle Identification Number

        Returns:
            Dict containing following status
        """
        url = f"{self.BASE_URL}/vehicle/is_following/{vin}"
        response = self.session.get(url)
        response.raise_for_status()
        return response.json()

    def search_vehicles(self, query: str) -> Dict[str, Any]:
        """
        Search for vehicles by query string.

        Args:
            query: Search query (can be VIN, make, model, etc.)

        Returns:
            Dict containing search results
        """
        url = f"{self.BASE_URL}/vehicle/search"
        params = {"q": query}
        response = self.session.get(url, params=params)
        response.raise_for_status()
        return response.json()

    def follow_vehicle(self, vin: str) -> Dict[str, Any]:
        """
        Follow a vehicle.

        Args:
            vin: The Vehicle Identification Number

        Returns:
            Dict containing response
        """
        url = f"{self.BASE_URL}/vehicle/follow/{vin}"
        response = self.session.post(url)
        response.raise_for_status()
        return response.json()

    def unfollow_vehicle(self, vin: str) -> Dict[str, Any]:
        """
        Unfollow a vehicle.

        Args:
            vin: The Vehicle Identification Number

        Returns:
            Dict containing response
        """
        url = f"{self.BASE_URL}/vehicle/unfollow/{vin}"
        response = self.session.post(url)
        response.raise_for_status()
        return response.json()


def main():
    """
    Example usage of the VinWiki client.
    Credentials should be provided via environment variables.
    """
    # Get credentials from environment variables
    email = os.getenv("VINWIKI_EMAIL")
    password = os.getenv("VINWIKI_PASSWORD")
    token = os.getenv("VINWIKI_TOKEN")  # Optional: use existing token

    if not email or not password:
        if not token:
            print("Error: VINWIKI_EMAIL and VINWIKI_PASSWORD environment variables must be set")
            print("OR provide VINWIKI_TOKEN to skip login")
            sys.exit(1)

    # Initialize client
    client = VinWikiClient(email or "", password or "")

    try:
        # Login or set token
        if token:
            print("Using provided token...")
            client.set_token(token)
        else:
            print("Logging in...")
            login_result = client.login()
            print(f"Login result: {login_result}")

        # Test: Get notification count
        print("\n--- Notification Count ---")
        notifications = client.get_notification_count()
        print(f"Unseen notifications: {notifications.get('notification_count', {}).get('unseen', 0)}")

        # Test: Get recent VINs
        print("\n--- Recent VINs ---")
        recent = client.get_recent_vins()
        for vehicle in recent.get("recent_vins", [])[:3]:
            print(f"- {vehicle['long_name']} (VIN: {vehicle['vin']})")

        # Test: Search for a vehicle
        print("\n--- Search: 'Ford GT' ---")
        search_results = client.search_vehicles("Ford GT")
        for vehicle in search_results.get("results", {}).get("vehicles", [])[:3]:
            print(f"- {vehicle['long_name']} (VIN: {vehicle['vin']})")

        # Test: Get specific VIN details
        if recent.get("recent_vins"):
            test_vin = recent["recent_vins"][0]["vin"]
            print(f"\n--- Vehicle Details: {test_vin} ---")
            vehicle_info = client.get_vehicle_by_vin(test_vin)
            vehicle = vehicle_info.get("vehicle", {})
            print(f"Make: {vehicle.get('make')}")
            print(f"Model: {vehicle.get('model')}")
            print(f"Year: {vehicle.get('year')}")
            print(f"Followers: {vehicle.get('follower_count')}")
            print(f"Posts: {vehicle.get('post_count')}")

            # Get vehicle feed
            print(f"\n--- Vehicle Feed: {test_vin} ---")
            feed = client.get_vehicle_feed(test_vin)
            for post in feed.get("feed", [])[:3]:
                post_data = post.get("post", {})
                print(f"- [{post_data.get('post_date_ago')}] {post_data.get('post_text')}")

        print("\n✓ All tests completed successfully!")

    except requests.HTTPError as e:
        print(f"HTTP Error: {e}")
        print(f"Response: {e.response.text if hasattr(e, 'response') else 'N/A'}")
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
