"""
MyDesigns.io API Client

A comprehensive Python client for the MyDesigns.io internal API.
Base URL: https://api.mydesigns.io
Auth URL: https://accounts.mydesigns.io

Authentication:
  MyDesigns uses Ory (accounts.mydesigns.io) as its identity provider.
  Two auth methods are supported:

  1. Cookie-based (session): Login via the Ory flow, then use cookies for all API calls.
  2. Personal Access Token (Bearer): Generate a PAT via the UI or API, then pass it as
     a base64-encoded JSON header: Authorization: Bearer <base64({"id": <id>, "value": "<value>"})>

Usage:
  client = MyDesignsClient()
  client.login("your_email@example.com", "your_password")

  # Get user profile
  me = client.get_me()

  # Generate a personal access token (for headless use)
  token = client.create_personal_access_token("my-script-token")
  # token["bearer"] contains the ready-to-use bearer string

  # Use with bearer token (no login needed if you have a PAT)
  client2 = MyDesignsClient(bearer_token="<your-bearer-token>")
  me = client2.get_me()
"""

import base64
import json
import time
from typing import Any, Dict, List, Optional, Union

import requests


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ACCOUNTS_BASE_URL = "https://accounts.mydesigns.io"
API_BASE_URL = "https://api.mydesigns.io"


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _encode_pat(pat_id: int, pat_value: str) -> str:
    """Encode a PAT id+value into the Bearer token format MyDesigns expects."""
    payload = json.dumps({"id": pat_id, "value": pat_value})
    return base64.b64encode(payload.encode()).decode()


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------

class MyDesignsClient:
    """
    A full-featured client for the MyDesigns.io internal API.

    Parameters
    ----------
    email : str, optional
        Account email (used with login()).
    password : str, optional
        Account password (used with login()).
    bearer_token : str, optional
        Pre-existing Personal Access Token (base64-encoded JSON).
        If provided, login() is not required.
    session : requests.Session, optional
        Custom requests session to use.
    """

    def __init__(
        self,
        email: Optional[str] = None,
        password: Optional[str] = None,
        bearer_token: Optional[str] = None,
        session: Optional[requests.Session] = None,
    ):
        self._email = email
        self._password = password
        self._bearer_token = bearer_token
        self._session = session or requests.Session()

        # Shared headers for all API requests
        self._session.headers.update(
            {
                "Accept": "application/json",
                "Content-Type": "application/json",
                "Origin": "https://mydesigns.io",
                "Referer": "https://mydesigns.io/",
            }
        )

        if bearer_token:
            self._session.headers["Authorization"] = f"Bearer {bearer_token}"

    # ------------------------------------------------------------------
    # Authentication
    # ------------------------------------------------------------------

    def login(
        self,
        email: Optional[str] = None,
        password: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Log in to MyDesigns.io via the Ory authentication flow.

        This performs a two-step Ory "identifier_first" login:
          1. POST the email to discover the login method.
          2. POST the password to complete authentication.

        On success the session cookies are stored and all subsequent API
        calls will be authenticated automatically.

        Parameters
        ----------
        email : str, optional
            Overrides the email provided at construction time.
        password : str, optional
            Overrides the password provided at construction time.

        Returns
        -------
        dict
            The Ory session object on success.

        Raises
        ------
        ValueError
            If email or password is missing.
        requests.HTTPError
            If the Ory service returns an error status.
        RuntimeError
            If the login flow cannot be completed.
        """
        email = email or self._email
        password = password or self._password
        if not email or not password:
            raise ValueError("email and password are required for login()")

        # ---- Step 1: Initiate the Ory browser login flow ----
        # We request a new login flow from accounts.mydesigns.io.
        init_url = (
            f"{ACCOUNTS_BASE_URL}/self-service/login/browser"
            "?return_to=https%3A%2F%2Fmydesigns.io%2Fapp%2Fdashboard%3Fpost-login%3Dtrue"
        )
        resp = self._session.get(init_url, allow_redirects=True)

        # The final URL contains the flow ID
        flow_url = resp.url  # e.g. https://accounts.mydesigns.io/login?flow=<uuid>
        if "flow=" not in flow_url:
            # Try to parse from response JSON
            try:
                data = resp.json()
                flow_id = data.get("id")
            except Exception:
                flow_id = None
            if not flow_id:
                raise RuntimeError(
                    f"Could not extract flow ID from redirect URL: {flow_url}"
                )
        else:
            flow_id = flow_url.split("flow=")[1].split("&")[0]

        # ---- Step 2: Get the flow to obtain the CSRF token ----
        flow_endpoint = (
            f"{ACCOUNTS_BASE_URL}/self-service/login/flows?id={flow_id}"
        )
        flow_resp = self._session.get(
            flow_endpoint, headers={"Accept": "application/json"}
        )
        flow_resp.raise_for_status()
        flow_data = flow_resp.json()

        csrf_token = None
        for node in flow_data.get("ui", {}).get("nodes", []):
            attrs = node.get("attributes", {})
            if attrs.get("name") == "csrf_token":
                csrf_token = attrs.get("value")
                break

        if not csrf_token:
            raise RuntimeError("Could not extract CSRF token from login flow")

        action_url = f"{ACCOUNTS_BASE_URL}/self-service/login?flow={flow_id}"

        # ---- Step 3: Submit the identifier (email) first ----
        step1_body = {
            "csrf_token": csrf_token,
            "method": "identifier_first",
            "identifier": email,
        }
        step1_resp = self._session.post(
            action_url,
            json=step1_body,
            headers={"Accept": "application/json"},
        )

        # If 200, the response contains the updated flow with a new CSRF token
        step1_data = step1_resp.json()

        # Extract new CSRF token from step 1 response
        new_csrf = csrf_token
        for node in step1_data.get("ui", {}).get("nodes", []):
            attrs = node.get("attributes", {})
            if attrs.get("name") == "csrf_token":
                new_csrf = attrs.get("value")
                break

        # ---- Step 4: Submit the password ----
        step2_body = {
            "csrf_token": new_csrf,
            "method": "password",
            "identifier": email,
            "password": password,
        }
        step2_resp = self._session.post(
            action_url,
            json=step2_body,
            headers={"Accept": "application/json"},
        )
        step2_resp.raise_for_status()
        session_data = step2_resp.json()

        if "session" not in session_data:
            raise RuntimeError(
                f"Login failed. Response: {json.dumps(session_data)[:500]}"
            )

        return session_data["session"]

    def logout(self) -> bool:
        """
        Log out of the current session.

        Returns
        -------
        bool
            True on success.
        """
        resp = self._session.get(
            f"{ACCOUNTS_BASE_URL}/self-service/logout/browser",
            headers={"Accept": "application/json"},
        )
        if resp.status_code in (200, 302):
            self._session.cookies.clear()
            return True
        return False

    def whoami(self) -> Dict[str, Any]:
        """
        Return the current Ory session information.

        Returns
        -------
        dict
            Ory session data including identity traits.
        """
        resp = self._session.get(
            f"{ACCOUNTS_BASE_URL}/sessions/whoami",
            headers={"Accept": "application/json"},
        )
        resp.raise_for_status()
        return resp.json()

    # ------------------------------------------------------------------
    # Internal HTTP helpers
    # ------------------------------------------------------------------

    def _get(self, path: str, params: Optional[Dict] = None) -> Any:
        """GET request against api.mydesigns.io."""
        resp = self._session.get(f"{API_BASE_URL}{path}", params=params)
        resp.raise_for_status()
        return resp.json() if resp.content else {}

    def _post(self, path: str, body: Optional[Dict] = None, params: Optional[Dict] = None) -> Any:
        """POST request against api.mydesigns.io."""
        resp = self._session.post(
            f"{API_BASE_URL}{path}", json=body, params=params
        )
        resp.raise_for_status()
        return resp.json() if resp.content else {}

    def _put(self, path: str, body: Optional[Dict] = None) -> Any:
        """PUT request against api.mydesigns.io."""
        resp = self._session.put(f"{API_BASE_URL}{path}", json=body)
        resp.raise_for_status()
        return resp.json() if resp.content else {}

    def _patch(self, path: str, body: Optional[Dict] = None) -> Any:
        """PATCH request against api.mydesigns.io."""
        resp = self._session.patch(f"{API_BASE_URL}{path}", json=body)
        resp.raise_for_status()
        return resp.json() if resp.content else {}

    def _delete(self, path: str) -> Any:
        """DELETE request against api.mydesigns.io."""
        resp = self._session.delete(f"{API_BASE_URL}{path}")
        resp.raise_for_status()
        return resp.json() if resp.content else {}

    # ------------------------------------------------------------------
    # Users
    # ------------------------------------------------------------------

    def get_me(self) -> Dict[str, Any]:
        """
        Get the current authenticated user's profile.

        Returns
        -------
        dict
            User object with id, name, email, roles, credits, extensions, etc.
        """
        return self._get("/users/me")

    def update_me(self, name: Optional[str] = None, **kwargs) -> Dict[str, Any]:
        """
        Update the current user's profile.

        Parameters
        ----------
        name : str, optional
            New display name.
        **kwargs
            Additional fields to update.

        Returns
        -------
        dict
            Updated user object.
        """
        body = {}
        if name is not None:
            body["name"] = name
        body.update(kwargs)
        return self._put("/users/me/update", body)

    def update_address(
        self,
        receipt: Optional[str] = None,
        address1: Optional[str] = None,
        address2: Optional[str] = None,
        city: Optional[str] = None,
        region: Optional[str] = None,
        postal_code: Optional[str] = None,
        country_code: Optional[str] = None,
        phone: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Update the current user's shipping/billing address.
        """
        body = {}
        if receipt is not None:
            body["receipt"] = receipt
        if address1 is not None:
            body["address1"] = address1
        if address2 is not None:
            body["address2"] = address2
        if city is not None:
            body["city"] = city
        if region is not None:
            body["region"] = region
        if postal_code is not None:
            body["postalCode"] = postal_code
        if country_code is not None:
            body["countryCode"] = country_code
        if phone is not None:
            body["phone"] = phone
        return self._put("/users/me/update-address", body)

    def get_user_info(self, user_ids: List[int]) -> List[Dict[str, Any]]:
        """
        Get basic info for one or more users by ID.

        Parameters
        ----------
        user_ids : list[int]
            List of user IDs to look up.

        Returns
        -------
        list[dict]
            User info objects.
        """
        params = [("ids", uid) for uid in user_ids]
        resp = self._session.get(f"{API_BASE_URL}/users/info", params=params)
        resp.raise_for_status()
        return resp.json()

    def get_credits(self) -> Dict[str, Any]:
        """
        Get the current user's credit balance.

        Returns
        -------
        dict
            Credits balance information.
        """
        return self._get("/users/me/credits")

    def get_invitation_link(self) -> Dict[str, Any]:
        """
        Get the current user's referral/invitation link.
        """
        return self._get("/users/me/invitation-link")

    def track_onboarding_event(self, event_name: str) -> Dict[str, Any]:
        """
        Track an onboarding event for the current user.
        """
        return self._post("/users/me/track-onboarding-event", {"event": event_name})

    # ------------------------------------------------------------------
    # Personal Access Tokens
    # ------------------------------------------------------------------

    def list_personal_access_tokens(self) -> List[Dict[str, Any]]:
        """
        List all personal access tokens for the current user.

        Returns
        -------
        list[dict]
            List of PAT objects with id and name (value is never returned after creation).
        """
        return self._get("/users/me/personal-access-tokens")

    def create_personal_access_token(self, name: str) -> Dict[str, Any]:
        """
        Create a new personal access token.

        The token value is only available immediately after creation.
        MyDesigns does not store or return the value again for security reasons.

        Parameters
        ----------
        name : str
            A human-readable label for this token.

        Returns
        -------
        dict
            Contains:
            - ``raw_response``: the raw base64-encoded token returned by the API
            - ``id``: the token ID
            - ``value``: the raw token value (store this safely)
            - ``bearer``: the ready-to-use Bearer token string for Authorization header
        """
        raw = self._post("/users/me/personal-access-tokens", {"name": name})
        # The API returns a base64-encoded JSON: {"id": <int>, "value": "<str>"}
        try:
            decoded = json.loads(base64.b64decode(raw).decode())
            bearer = raw  # The raw base64 IS the bearer token
            return {
                "raw_response": raw,
                "id": decoded["id"],
                "value": decoded["value"],
                "bearer": bearer,
            }
        except Exception:
            return {"raw_response": raw}

    def delete_personal_access_token(self, token_id: int) -> bool:
        """
        Delete (revoke) a personal access token.

        Parameters
        ----------
        token_id : int
            The ID of the token to delete.

        Returns
        -------
        bool
            True on success.
        """
        self._delete(f"/users/me/personal-access-tokens/{token_id}")
        return True

    # ------------------------------------------------------------------
    # Designs / Listings
    # ------------------------------------------------------------------

    def get_categories(self) -> List[Dict[str, Any]]:
        """
        Get all listing categories (collections/sub-collections).

        Returns
        -------
        list[dict]
            Category objects with id, categoryId, name, designsCount.
        """
        return self._get("/categories")

    def get_designs(
        self,
        category_id: int,
        page: int = 1,
        search: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Get designs within a specific category.

        Parameters
        ----------
        category_id : int
            The category (collection) ID to list designs from.
        page : int, optional
            Page number (default 1).
        search : str, optional
            Search query to filter designs.

        Returns
        -------
        list[dict]
            Design objects.
        """
        params = {"categoryId": category_id, "page": page}
        if search:
            params["search"] = search
        return self._get("/designs", params=params)

    def get_jobs(self, marker: int = 0) -> List[Dict[str, Any]]:
        """
        Get background job statuses.

        Parameters
        ----------
        marker : int, optional
            Job ID to start listing from.

        Returns
        -------
        list[dict]
            Job objects.
        """
        return self._get("/jobs", params={"marker": marker})

    def get_imported_designs(self) -> List[Dict[str, Any]]:
        """
        Get designs imported from external sources.
        """
        return self._get("/listings/imported-designs")

    def get_tutorials(self) -> List[Dict[str, Any]]:
        """
        Get tutorial items.
        """
        return self._get("/tutorials")

    # ------------------------------------------------------------------
    # Products
    # ------------------------------------------------------------------

    def get_products(self, **params) -> List[Dict[str, Any]]:
        """
        Get products.

        Returns
        -------
        list[dict]
            Product objects.
        """
        return self._get("/products", params=params)

    def get_product(self, product_id: int) -> Dict[str, Any]:
        """
        Get a single product by ID.
        """
        return self._get(f"/products/{product_id}")

    def delete_product(self, product_id: int) -> bool:
        """Delete a product by ID."""
        self._delete(f"/products/{product_id}")
        return True

    def delete_products(self, product_ids: List[int]) -> Dict[str, Any]:
        """Bulk delete products."""
        return self._post("/products/delete", {"ids": product_ids})

    def get_product_files(self, product_id: int) -> List[Dict[str, Any]]:
        """Get all files associated with a product."""
        return self._get(f"/products/{product_id}/files")

    def get_product_items(self, product_id: int) -> List[Dict[str, Any]]:
        """Get all items (variants) for a product."""
        return self._get(f"/products/{product_id}/items")

    def get_product_print_files(self, product_id: int) -> List[Dict[str, Any]]:
        """Get print files for a product."""
        return self._get(f"/products/{product_id}/print-files")

    def regenerate_mockups(self, product_id: int) -> Dict[str, Any]:
        """Trigger mockup regeneration for a product."""
        return self._post(f"/products/{product_id}/regenerate-mockups")

    def resync_product(self, product_id: int) -> Dict[str, Any]:
        """Resync a product with its source."""
        return self._post(f"/products/{product_id}/resync")

    def get_product_status(self, product_id: int) -> Dict[str, Any]:
        """Get the current publish/sync status of a product."""
        return self._get(f"/products/{product_id}/status")

    # Bulk products
    def get_bulk_product(self, bulk_id: int) -> Dict[str, Any]:
        """Get a bulk product group."""
        return self._get(f"/products/bulk/{bulk_id}")

    def create_bulk_product(self, **kwargs) -> Dict[str, Any]:
        """Create a new bulk product."""
        return self._post("/products/bulk", kwargs)

    def clone_bulk_product(self, bulk_id: int) -> Dict[str, Any]:
        """Clone a bulk product group."""
        return self._post(f"/products/bulk/{bulk_id}/clone")

    def delete_bulk_products(self, bulk_ids: List[int]) -> Dict[str, Any]:
        """Delete bulk products."""
        return self._post("/products/bulk/delete", {"ids": bulk_ids})

    # ------------------------------------------------------------------
    # Orders
    # ------------------------------------------------------------------

    def get_orders(self, **params) -> Dict[str, Any]:
        """
        Get orders.

        Parameters
        ----------
        **params
            Query parameters (e.g., page, status, providerUserId).

        Returns
        -------
        dict
            Paginated order list.
        """
        return self._get("/orders", params=params)

    def get_order(self, order_id: int) -> Dict[str, Any]:
        """Get a single order by ID."""
        return self._get(f"/orders/{order_id}")

    def get_external_orders(self, **params) -> Dict[str, Any]:
        """Get external (marketplace) orders."""
        return self._get("/orders/external", params=params)

    def get_recent_orders(
        self,
        days_ago: int = 30,
        provider_id: int = 0,
        orders_type: str = "all",
    ) -> List[Dict[str, Any]]:
        """
        Get recent orders within a time window.

        Parameters
        ----------
        days_ago : int
            How many days back to look.
        provider_id : int
            Filter by provider user ID (0 = all).
        orders_type : str
            One of 'all', 'pod', 'digital'.
        """
        return self._get(
            "/orders/recent",
            params={
                "daysAgo": days_ago,
                "providerId": provider_id,
                "ordersType": orders_type,
            },
        )

    def get_orders_by_status(
        self,
        status: str,
        provider_user_id: int = 0,
        page: int = 1,
    ) -> Dict[str, Any]:
        """
        Get orders filtered by status.

        Parameters
        ----------
        status : str
            Order status. Known values: CREATED, FAILED_TO_CHARGE.
        provider_user_id : int
            Filter by provider user (0 = all).
        page : int
            Page number.
        """
        return self._get(
            "/orders/status",
            params={
                "providerUserId": provider_user_id,
                "status": status,
                "page": page,
            },
        )

    def get_top_sold_publications(
        self, days_ago: int = 30
    ) -> List[Dict[str, Any]]:
        """Get the top-selling publications over the last N days."""
        return self._get(
            "/orders/top-sold-publications", params={"daysAgo": days_ago}
        )

    def get_order_thumbnail(self, order_id: int) -> Dict[str, Any]:
        """Get the thumbnail URL for an order."""
        return self._get(f"/orders/{order_id}/thumbnail")

    def approve_order(self, order_id: int) -> Dict[str, Any]:
        """Approve a pending order."""
        return self._post(f"/orders/{order_id}/approve")

    def cancel_order(self, order_id: int) -> Dict[str, Any]:
        """Cancel an order."""
        return self._post(f"/orders/{order_id}/cancel")

    def add_order_note(self, order_id: int, note: str) -> Dict[str, Any]:
        """Add a note to an order."""
        return self._post(f"/orders/{order_id}/note", {"note": note})

    def retry_order_charge(self, order_id: int) -> Dict[str, Any]:
        """Retry charging a failed order."""
        return self._post(f"/orders/{order_id}/retry-charge")

    def calculate_shipping(self, **kwargs) -> Dict[str, Any]:
        """Calculate shipping cost for an order."""
        return self._post("/orders/calculate-shipping", kwargs)

    def export_orders(self, **kwargs) -> Dict[str, Any]:
        """Export orders as a CSV/report."""
        return self._post("/orders/export", kwargs)

    # ------------------------------------------------------------------
    # Publications
    # ------------------------------------------------------------------

    def get_publications(self, page_index: int = 1, **params) -> Dict[str, Any]:
        """
        Get all publications (published listings).

        Parameters
        ----------
        page_index : int
            Page number.

        Returns
        -------
        dict
            Paginated publication list.
        """
        params["pageIndex"] = page_index
        return self._get("/publications", params=params)

    def check_publications_status(self, publication_ids: List[int]) -> Dict[str, Any]:
        """Check the live status of one or more publications."""
        return self._post(
            "/publications/check-publications-status",
            {"publicationIds": publication_ids},
        )

    def delete_publications(self, publication_ids: List[int]) -> Dict[str, Any]:
        """Bulk delete publications."""
        return self._post(
            "/publications/delete-publications",
            {"publicationIds": publication_ids},
        )

    def get_publication_groups(self) -> List[Dict[str, Any]]:
        """Get publication groups."""
        return self._get("/publications/groups")

    def get_pod_publication_preview(
        self, design_publication_id: int
    ) -> Dict[str, Any]:
        """Get the mockup preview for a POD publication."""
        return self._get(f"/publications/pod/{design_publication_id}/preview")

    def get_digital_publication_preview(
        self, design_publication_id: int
    ) -> Dict[str, Any]:
        """Get the preview for a digital publication."""
        return self._get(f"/publications/digital/{design_publication_id}/preview")

    def get_pod_publication_print_areas(
        self, design_publication_id: int
    ) -> Dict[str, Any]:
        """Get print areas for a POD publication."""
        return self._get(f"/publications/pod/{design_publication_id}/print-areas")

    def get_user_profiles(self) -> List[Dict[str, Any]]:
        """Get all publication user profiles (shop-specific metadata)."""
        return self._get("/publications/user-profiles")

    def get_user_profile(self, profile_id: int) -> Dict[str, Any]:
        """Get a single publication user profile."""
        return self._get(f"/publications/user-profile/{profile_id}")

    def update_user_profile(
        self, profile_id: int, **kwargs
    ) -> Dict[str, Any]:
        """Update a publication user profile."""
        return self._put(f"/publications/user-profile/{profile_id}", kwargs)

    # ------------------------------------------------------------------
    # Providers / Shops
    # ------------------------------------------------------------------

    def get_providers(self) -> List[Dict[str, Any]]:
        """
        Get all connected provider integrations (Etsy, Shopify, etc.).

        Returns
        -------
        list[dict]
            Provider objects describing each connected shop/marketplace.
        """
        return self._get("/providers")

    def get_provider_users(self) -> List[Dict[str, Any]]:
        """
        Get all provider user accounts (shop connections).

        Returns
        -------
        list[dict]
            Connected shop/account objects.
        """
        return self._get("/providers/provider-users")

    def get_provider_payment_method(self, provider_user_id: int) -> Dict[str, Any]:
        """Get payment method for a provider user."""
        return self._get(f"/providers/payment-method/{provider_user_id}")

    def get_provider_shop_address(self, provider_user_id: int) -> Dict[str, Any]:
        """Get shop address for a provider user."""
        return self._get(f"/providers/shop-address/{provider_user_id}")

    def get_self_fulfillment(self, provider_user_id: int) -> Dict[str, Any]:
        """Get self-fulfillment settings for a provider user."""
        return self._get(f"/providers/self-fulfillment/{provider_user_id}")

    # ------------------------------------------------------------------
    # Print Partners
    # ------------------------------------------------------------------

    def get_print_partner_users(self, user_id: int) -> Dict[str, Any]:
        """
        Get print partner user connections for a user.

        Parameters
        ----------
        user_id : int
            The MyDesigns user ID.
        """
        return self._get(f"/print-partners/print-partner-users/{user_id}")

    def get_cost_analysis(
        self, partner_code: str, **params
    ) -> Dict[str, Any]:
        """
        Get cost analysis for a print partner.

        Parameters
        ----------
        partner_code : str
            The print partner code (e.g. 'printify').
        """
        return self._get(f"/print-partners/cost-analysis/{partner_code}", params=params)

    def get_saved_cost_analysis(self, partner_code: str) -> Dict[str, Any]:
        """Get saved cost analysis for a print partner."""
        return self._get(f"/print-partners/cost-analysis/{partner_code}/saved")

    def get_cost_analysis_shipping(self, partner_code: str) -> Dict[str, Any]:
        """Get shipping cost analysis for a print partner."""
        return self._get(f"/print-partners/cost-analysis/{partner_code}/shipping")

    # ------------------------------------------------------------------
    # Mockups
    # ------------------------------------------------------------------

    def get_mockups(
        self,
        sort: str = "RECENT",
        official: bool = False,
        enabled_only: bool = False,
        valid_only: bool = False,
        page: int = 1,
        **params,
    ) -> Dict[str, Any]:
        """
        List mockup templates.

        Parameters
        ----------
        sort : str
            Sort order. Known values: RECENT, POPULAR.
        official : bool
            Only return official mockups.
        enabled_only : bool
            Only return enabled mockups.
        valid_only : bool
            Only return valid mockups.
        page : int
            Page number.

        Returns
        -------
        dict
            Paginated mockup list.
        """
        params.update(
            {
                "sort": sort,
                "official": str(official).lower(),
                "enabledOnly": str(enabled_only).lower(),
                "validOnly": str(valid_only).lower(),
                "page": page,
            }
        )
        return self._get("/integrations/mockups", params=params)

    def get_mockup(self, mockup_id: int) -> Dict[str, Any]:
        """Get a single mockup by ID."""
        return self._get(f"/integrations/mockups/{mockup_id}")

    def get_mockup_categories(self) -> List[Dict[str, Any]]:
        """Get all mockup categories."""
        return self._get("/integrations/mockups/categories")

    def get_mockup_profiles(self) -> List[Dict[str, Any]]:
        """Get saved mockup profiles."""
        return self._get("/integrations/mockups/profiles")

    def generate_mockup_preview(
        self, mockup_id: int, **kwargs
    ) -> Dict[str, Any]:
        """
        Generate a preview for a mockup.

        Parameters
        ----------
        mockup_id : int
            The mockup template ID.
        **kwargs
            Additional body parameters (e.g., design file info).
        """
        return self._post(
            f"/integrations/mockups/{mockup_id}/generate-preview", kwargs
        )

    def favorite_mockup(self, mockup_id: int) -> Dict[str, Any]:
        """Toggle favorite status on a mockup."""
        return self._post(f"/integrations/mockups/{mockup_id}/favorite")

    def download_mockup(self, mockup_id: int) -> Dict[str, Any]:
        """Get download URL for a mockup."""
        return self._get(f"/integrations/mockups/{mockup_id}/download")

    # ------------------------------------------------------------------
    # Dream AI
    # ------------------------------------------------------------------

    def get_dream_images(
        self,
        keywords: str = "",
        page_index: int = 1,
        **params,
    ) -> Dict[str, Any]:
        """
        Get AI-generated dream images.

        Parameters
        ----------
        keywords : str
            Keyword filter.
        page_index : int
            Page number.

        Returns
        -------
        dict
            Paginated dream image list.
        """
        params.update({"keywords": keywords, "pageIndex": page_index})
        return self._get("/integrations/dreamer/dream-images", params=params)

    # ------------------------------------------------------------------
    # Canvas
    # ------------------------------------------------------------------

    def get_canvas_size_presets(self) -> List[Dict[str, Any]]:
        """Get canvas size presets."""
        return self._get("/integrations/canvas/size-presets")

    def create_canvas_size_preset(self, **kwargs) -> Dict[str, Any]:
        """Create a custom canvas size preset."""
        return self._post("/integrations/canvas/size-presets", kwargs)

    def delete_canvas_size_preset(self, preset_id: int) -> bool:
        """Delete a canvas size preset."""
        self._delete(f"/integrations/canvas/size-presets/{preset_id}")
        return True

    def get_canvas_fonts(self) -> List[Dict[str, Any]]:
        """Get all available fonts for the Canvas editor."""
        return self._get("/integrations/canvas/fonts")

    def get_canvas_custom_fonts(self) -> List[Dict[str, Any]]:
        """Get custom uploaded fonts."""
        return self._get("/integrations/canvas/fonts/custom")

    def favorite_canvas_font(self, font_id: int) -> Dict[str, Any]:
        """Toggle favorite on a canvas font."""
        return self._post(f"/integrations/canvas/fonts/{font_id}/favorite")

    def get_canvas_illustrations(self, **params) -> List[Dict[str, Any]]:
        """Get canvas illustration assets."""
        return self._get("/integrations/canvas/illustrations", params=params)

    def get_canvas_illustration_categories(self) -> List[Dict[str, Any]]:
        """Get illustration categories."""
        return self._get("/integrations/canvas/illustration-categories")

    def render_canvas_scene(self, **kwargs) -> Dict[str, Any]:
        """Render a canvas scene to an image."""
        return self._post("/integrations/canvas/render-scene", kwargs)

    def save_canvas_design(self, **kwargs) -> Dict[str, Any]:
        """Save the current canvas as a design."""
        return self._post("/integrations/canvas/store", kwargs)

    def bulk_edit_canvas_listings(self, **kwargs) -> Dict[str, Any]:
        """Bulk edit listings from the canvas view."""
        return self._post("/integrations/canvas/bulk-edit-listings", kwargs)

    # ------------------------------------------------------------------
    # Files & Assets
    # ------------------------------------------------------------------

    def sign_file_upload(self, **kwargs) -> Dict[str, Any]:
        """
        Get a pre-signed URL for uploading a file.

        Returns
        -------
        dict
            Contains signed upload URL and file metadata.
        """
        return self._post("/files/sign", kwargs)

    def get_file(self, file_guid: str) -> Dict[str, Any]:
        """
        Get information about an uploaded file.

        Parameters
        ----------
        file_guid : str
            The file GUID.
        """
        return self._get(f"/files/{file_guid}")

    def delete_file(self, file_guid: str) -> bool:
        """Delete an uploaded file."""
        self._delete(f"/files/{file_guid}")
        return True

    def get_asset_folders(self) -> List[Dict[str, Any]]:
        """Get asset storage folders."""
        return self._get("/assets/folders")

    def get_image_patterns(self) -> List[Dict[str, Any]]:
        """Get available image pattern assets."""
        return self._get("/image-patterns")

    def get_color_profiles(self) -> List[Dict[str, Any]]:
        """Get saved color profiles."""
        return self._get("/color-profiles")

    def add_color_profile(self, **kwargs) -> Dict[str, Any]:
        """Add a new color profile."""
        return self._post("/color-profiles/add", kwargs)

    # ------------------------------------------------------------------
    # Etsy Integration
    # ------------------------------------------------------------------

    def get_etsy_seller_taxonomies(self) -> List[Dict[str, Any]]:
        """Get Etsy product taxonomy (categories)."""
        return self._get("/integrations/etsy/seller-taxonomies")

    def get_etsy_shipping_profiles(self, provider_user_id: int) -> List[Dict[str, Any]]:
        """Get Etsy shipping profiles for a shop."""
        return self._get(
            "/integrations/etsy/shop/shipping-profiles",
            params={"providerUserId": provider_user_id},
        )

    def get_etsy_default_shipping_profile(self) -> Dict[str, Any]:
        """Get the default Etsy shipping profile."""
        return self._get("/integrations/etsy/default-shipping-profile")

    def get_etsy_shop_sections(self, provider_user_id: int) -> List[Dict[str, Any]]:
        """Get Etsy shop sections."""
        return self._get(
            "/integrations/etsy/shop/sections",
            params={"providerUserId": provider_user_id},
        )

    def connect_etsy(self, **kwargs) -> Dict[str, Any]:
        """Initiate Etsy OAuth connection."""
        return self._post("/integrations/etsy/connect", kwargs)

    def disconnect_etsy(self, provider_user_id: int) -> Dict[str, Any]:
        """Disconnect an Etsy shop."""
        return self._delete(f"/integrations/etsy/disconnect/{provider_user_id}")

    def publish_to_etsy_pod(self, **kwargs) -> Dict[str, Any]:
        """Publish a Print-on-Demand product to Etsy."""
        return self._post("/integrations/etsy/publish/pod", kwargs)

    def publish_to_etsy_digital(self, **kwargs) -> Dict[str, Any]:
        """Publish a digital product to Etsy."""
        return self._post("/integrations/etsy/publish/digital", kwargs)

    def import_etsy_listings(self, **kwargs) -> Dict[str, Any]:
        """Import existing Etsy listings."""
        return self._post("/integrations/etsy/listings/import", kwargs)

    def get_etsy_listing_variants(self, provider_user_id: int, **params) -> List[Dict[str, Any]]:
        """Get variants available for an Etsy listing."""
        params["providerUserId"] = provider_user_id
        return self._get("/integrations/etsy/listing/variants", params=params)

    def validate_etsy_fields(self, **kwargs) -> Dict[str, Any]:
        """Validate listing fields before publishing to Etsy."""
        return self._post("/integrations/etsy/validate/fields", kwargs)

    def validate_etsy_images(self, **kwargs) -> Dict[str, Any]:
        """Validate listing images before publishing to Etsy."""
        return self._post("/integrations/etsy/validate/images", kwargs)

    # ------------------------------------------------------------------
    # Shopify Integration
    # ------------------------------------------------------------------

    def connect_shopify_app(self, shop_domain: str) -> Dict[str, Any]:
        """Connect a Shopify store via OAuth."""
        return self._post("/integrations/shopify/app/connect", {"shop": shop_domain})

    def disconnect_shopify(self, provider_user_id: int) -> Dict[str, Any]:
        """Disconnect a Shopify store."""
        return self._post(f"/integrations/shopify/app/uninstall/{provider_user_id}")

    def get_shopify_categories(self, **params) -> List[Dict[str, Any]]:
        """Get Shopify product categories/collections."""
        return self._get("/integrations/shopify/categories", params=params)

    def get_shopify_collections(self, provider_user_id: int) -> List[Dict[str, Any]]:
        """Get Shopify collections for a shop."""
        return self._get(
            "/integrations/shopify/shop/collections",
            params={"providerUserId": provider_user_id},
        )

    def get_shopify_delivery_profiles(self, provider_user_id: int) -> List[Dict[str, Any]]:
        """Get Shopify delivery profiles."""
        return self._get(
            "/integrations/shopify/shop/delivery-profiles",
            params={"providerUserId": provider_user_id},
        )

    def publish_to_shopify_pod(self, **kwargs) -> Dict[str, Any]:
        """Publish a POD product to Shopify."""
        return self._post("/integrations/shopify/publish/pod", kwargs)

    def publish_to_shopify_digital(self, **kwargs) -> Dict[str, Any]:
        """Publish a digital product to Shopify."""
        return self._post("/integrations/shopify/publish/digital", kwargs)

    def import_shopify_listings(self, **kwargs) -> Dict[str, Any]:
        """Import existing Shopify products."""
        return self._post("/integrations/shopify/listings/import", kwargs)

    def validate_shopify_fields(self, **kwargs) -> Dict[str, Any]:
        """Validate listing fields before publishing to Shopify."""
        return self._post("/integrations/shopify/validate/fields", kwargs)

    # ------------------------------------------------------------------
    # WooCommerce Integration
    # ------------------------------------------------------------------

    def connect_woocommerce(self, **kwargs) -> Dict[str, Any]:
        """Connect a WooCommerce store."""
        return self._post("/integrations/woocommerce/connect", kwargs)

    def disconnect_woocommerce(self, provider_user_id: int) -> Dict[str, Any]:
        """Disconnect a WooCommerce store."""
        return self._delete(f"/integrations/woocommerce/disconnect/{provider_user_id}")

    def publish_to_woocommerce_pod(self, **kwargs) -> Dict[str, Any]:
        """Publish a POD product to WooCommerce."""
        return self._post("/integrations/woocommerce/publish/pod", kwargs)

    def publish_to_woocommerce_digital(self, **kwargs) -> Dict[str, Any]:
        """Publish a digital product to WooCommerce."""
        return self._post("/integrations/woocommerce/publish/digital", kwargs)

    def get_woocommerce_categories(self, **params) -> List[Dict[str, Any]]:
        """Get WooCommerce product categories."""
        return self._get("/integrations/woocommerce/categories", params=params)

    def validate_woocommerce_fields(self, **kwargs) -> Dict[str, Any]:
        """Validate listing fields before publishing to WooCommerce."""
        return self._post("/integrations/woocommerce/validate/fields", kwargs)

    # ------------------------------------------------------------------
    # TikTok Shops Integration
    # ------------------------------------------------------------------

    def get_tiktok_auth_url(self) -> Dict[str, Any]:
        """Get the TikTok Shop OAuth authorization URL."""
        return self._get("/integrations/tiktokshops/auth-url")

    def disconnect_tiktok(self, provider_user_id: int) -> Dict[str, Any]:
        """Disconnect a TikTok Shop."""
        return self._delete(f"/integrations/tiktokshops/disconnect/{provider_user_id}")

    def publish_to_tiktok(self, **kwargs) -> Dict[str, Any]:
        """Publish a product to TikTok Shops."""
        return self._post("/integrations/tiktokshops/publish", kwargs)

    def get_tiktok_categories(self, provider_user_id: int) -> List[Dict[str, Any]]:
        """Get TikTok Shop product categories."""
        return self._get(
            "/integrations/tiktokshops/taxonomies",
            params={"providerUserId": provider_user_id},
        )

    def get_tiktok_brands(self, **params) -> List[Dict[str, Any]]:
        """Get TikTok Shop brands."""
        return self._get("/integrations/tiktokshops/brands", params=params)

    def get_tiktok_warehouses(self, provider_user_id: int) -> List[Dict[str, Any]]:
        """Get TikTok Shop warehouses."""
        return self._get(
            f"/integrations/tiktokshops/warehouses/{provider_user_id}"
        )

    def import_tiktok_listings(self, **kwargs) -> Dict[str, Any]:
        """Import TikTok Shop listings."""
        return self._post("/integrations/tiktokshops/listings/import", kwargs)

    def validate_tiktok_fields(self, **kwargs) -> Dict[str, Any]:
        """Validate listing fields before publishing to TikTok Shops."""
        return self._post("/integrations/tiktokshops/validate/fields", kwargs)

    # ------------------------------------------------------------------
    # Amazon Integration
    # ------------------------------------------------------------------

    def get_amazon_auth_uri(self, marketplace: str) -> Dict[str, Any]:
        """
        Get the Amazon OAuth URI for a specific marketplace.

        Parameters
        ----------
        marketplace : str
            Amazon marketplace code, e.g. 'US', 'UK', 'DE'.
        """
        return self._get(f"/integrations/amazon/auth-uri/{marketplace}")

    def disconnect_amazon(self, provider_user_id: int) -> Dict[str, Any]:
        """Disconnect an Amazon marketplace account."""
        return self._delete(f"/integrations/amazon/disconnect/{provider_user_id}")

    def publish_to_amazon(self, **kwargs) -> Dict[str, Any]:
        """Publish a product to Amazon."""
        return self._post("/integrations/amazon/publish", kwargs)

    def validate_amazon_fields(self, **kwargs) -> Dict[str, Any]:
        """Validate listing fields before publishing to Amazon."""
        return self._post("/integrations/amazon/validate/fields", kwargs)

    def validate_amazon_images(self, **kwargs) -> Dict[str, Any]:
        """Validate listing images before publishing to Amazon."""
        return self._post("/integrations/amazon/validate/images", kwargs)

    # ------------------------------------------------------------------
    # Printify Integration
    # ------------------------------------------------------------------

    def connect_printify(self, **kwargs) -> Dict[str, Any]:
        """Connect a Printify account."""
        return self._post("/integrations/printify/connect", kwargs)

    def disconnect_printify(self, print_partner_user_id: int) -> Dict[str, Any]:
        """Disconnect Printify."""
        return self._delete(f"/integrations/printify/disconnect/{print_partner_user_id}")

    def get_printify_blueprints(self, **params) -> List[Dict[str, Any]]:
        """Get Printify product blueprints."""
        return self._get("/integrations/printify/blueprints", params=params)

    def get_printify_blueprint(self, blueprint_id: int) -> Dict[str, Any]:
        """Get a specific Printify blueprint."""
        return self._get(f"/integrations/printify/blueprints/{blueprint_id}")

    def calculate_printify_cost(self, **kwargs) -> Dict[str, Any]:
        """Calculate Printify production cost."""
        return self._post("/integrations/printify/calculate-cost", kwargs)

    def generate_printify_mockups(self, **kwargs) -> Dict[str, Any]:
        """Generate mockups using Printify."""
        return self._post("/integrations/printify/generate-mockups", kwargs)

    # ------------------------------------------------------------------
    # POD Products
    # ------------------------------------------------------------------

    def get_pod_product_types(self) -> List[Dict[str, Any]]:
        """Get all available POD product types."""
        return self._get("/pod/products/types")

    def get_pod_product_variants(self, **params) -> List[Dict[str, Any]]:
        """Get variants for POD product types."""
        return self._get("/pod/products/variants", params=params)

    def get_pod_print_areas(self, **params) -> Dict[str, Any]:
        """Get print areas configuration."""
        return self._get("/pod/products/print-areas", params=params)

    # ------------------------------------------------------------------
    # AI Tools
    # ------------------------------------------------------------------

    def analyze_image_vision(self, **kwargs) -> Dict[str, Any]:
        """
        Analyze an image using Vision AI to generate tags, title, description.

        Parameters
        ----------
        **kwargs
            Request body. Typically includes 'imageUrl' or 'designId'.
        """
        return self._post("/integrations/vision/analyze-image", kwargs)

    def analyze_image_and_publish(self, **kwargs) -> Dict[str, Any]:
        """
        Analyze an image and apply the AI results to a publication.
        """
        return self._post("/integrations/vision/analyze-image-publish", kwargs)

    def translate_listing(self, **kwargs) -> Dict[str, Any]:
        """
        Translate listing text to another language.

        Parameters
        ----------
        **kwargs
            Request body including text and target language.
        """
        return self._post("/integrations/translate", kwargs)

    def check_trademark(self, text: str, **params) -> Dict[str, Any]:
        """
        Check text for trademark conflicts.

        Parameters
        ----------
        text : str
            The text to check.
        """
        return self._get(
            "/integrations/trademarks/check-text",
            params={"text": text, **params},
        )

    def bulk_check_trademarks(self, texts: List[str]) -> Dict[str, Any]:
        """Bulk trademark check for multiple texts."""
        return self._post("/integrations/trademarks/bulk-check", {"texts": texts})

    def search_pixabay(self, query: str, page: int = 1, **params) -> Dict[str, Any]:
        """
        Search for images on Pixabay (integrated).

        Parameters
        ----------
        query : str
            Search query.
        page : int
            Page number.
        """
        params.update({"q": query, "page": page})
        return self._get("/integrations/pixabay/images", params=params)

    def store_pixabay_image(self, pixabay_image_id: int, **kwargs) -> Dict[str, Any]:
        """
        Import a Pixabay image into MyDesigns storage.

        Parameters
        ----------
        pixabay_image_id : int
            The Pixabay image ID.
        """
        return self._post(f"/integrations/pixabay/images/{pixabay_image_id}/store", kwargs)

    def bulk_edit_listings(self, **kwargs) -> Dict[str, Any]:
        """
        Bulk edit multiple listings at once.
        """
        return self._post("/integrations/bulk-edit", kwargs)

    def vectorize_design(self, **kwargs) -> Dict[str, Any]:
        """
        Create a vectorized preview of a design.
        """
        return self._post("/designs/vectorize/create-preview", kwargs)

    # ------------------------------------------------------------------
    # Notifications
    # ------------------------------------------------------------------

    def get_notifications(self) -> List[Dict[str, Any]]:
        """
        Get notification deliveries for the current user.

        Returns
        -------
        list[dict]
            Notification objects.
        """
        return self._get("/notifications/deliveries")

    def mark_notifications_read(self, notification_ids: Optional[List[int]] = None) -> bool:
        """
        Mark notifications as read.

        Parameters
        ----------
        notification_ids : list[int], optional
            Specific notification IDs to mark read. If None, marks all.
        """
        body = {}
        if notification_ids:
            body["ids"] = notification_ids
        self._post("/notifications/read", body)
        return True

    def get_notification_preferences(self) -> Dict[str, Any]:
        """Get notification preferences."""
        return self._get("/notifications/preferences")

    def update_notification_preferences(self, **kwargs) -> Dict[str, Any]:
        """Update notification preferences."""
        return self._put("/notifications/preferences", kwargs)

    # ------------------------------------------------------------------
    # Reports
    # ------------------------------------------------------------------

    def get_report_preferences(self) -> Dict[str, Any]:
        """Get saved report preferences."""
        return self._get("/reports/preferences")

    def update_report_preferences(self, **kwargs) -> Dict[str, Any]:
        """Update report preferences."""
        return self._put("/reports/preferences", kwargs)

    # ------------------------------------------------------------------
    # Support / Community
    # ------------------------------------------------------------------

    def get_support_discussions(
        self,
        page_index: int = 1,
        status: str = "OPENED",
        **params,
    ) -> Dict[str, Any]:
        """
        Get support/community discussions.

        Parameters
        ----------
        page_index : int
            Page number.
        status : str
            Discussion status filter.
        """
        params.update({"pageIndex": page_index, "status": status})
        return self._get("/support/discussions", params=params)

    def get_discussion(self, discussion_id: int) -> Dict[str, Any]:
        """Get a single discussion."""
        return self._get(f"/support/discussions/{discussion_id}")

    def create_discussion(self, **kwargs) -> Dict[str, Any]:
        """Create a new support discussion."""
        return self._post("/support/discussions", kwargs)

    def get_circle_posts(
        self,
        circle_post_group: str,
        **params,
    ) -> List[Dict[str, Any]]:
        """
        Get posts from the community circle.

        Parameters
        ----------
        circle_post_group : str
            Group name, e.g. 'news', 'tuts_pod'.
        """
        params["circlePostGroup"] = circle_post_group
        return self._get("/support/circle/posts", params=params)

    def get_circle_events(self) -> List[Dict[str, Any]]:
        """Get upcoming community events from Circle."""
        return self._get("/support/circle/events")

    def get_intercom_hmac(self) -> Dict[str, Any]:
        """Get the HMAC for authenticating the Intercom chat widget."""
        return self._get("/support/intercom/hmac")

    # ------------------------------------------------------------------
    # Templates
    # ------------------------------------------------------------------

    def get_template(self, template_id: int) -> Dict[str, Any]:
        """
        Get a specific listing template.

        Parameters
        ----------
        template_id : int
            The template ID.
        """
        return self._get(f"/templates/{template_id}")

    # ------------------------------------------------------------------
    # Store (MyDesigns marketplace)
    # ------------------------------------------------------------------

    def get_my_store(self) -> Dict[str, Any]:
        """Get the current user's MyDesigns store settings."""
        return self._get("/stores/me")

    def get_store(self, slug: str) -> Dict[str, Any]:
        """Get a public MyDesigns store by slug."""
        return self._get(f"/stores/{slug}/public")

    def get_store_publications(self, slug: str, **params) -> Dict[str, Any]:
        """Get publications listed in a store."""
        return self._get(f"/stores/{slug}/publications", params=params)

    def get_store_stripe_status(self) -> Dict[str, Any]:
        """Get Stripe payout status for the current store."""
        return self._get("/stores/me/stripe/status")

    def get_store_stripe_dashboard_link(self) -> Dict[str, Any]:
        """Get a link to the Stripe Connect dashboard."""
        return self._get("/stores/me/stripe/dashboard")

    # ------------------------------------------------------------------
    # Wallets
    # ------------------------------------------------------------------

    def get_wallet_balance(self) -> Dict[str, Any]:
        """Get the current user's wallet balance."""
        return self._get("/wallets/me/balance")

    def get_wallet_transactions(self, **params) -> Dict[str, Any]:
        """Get wallet transaction history."""
        return self._get("/wallets/me/wallet-transactions", params=params)

    def get_wallet_auto_topup(self) -> Dict[str, Any]:
        """Get auto top-up settings."""
        return self._get("/wallets/me/auto-topup")

    def topup_wallet_checkout(self, **kwargs) -> Dict[str, Any]:
        """Initiate a wallet top-up via checkout."""
        return self._post("/wallets/me/wallet-topup/checkout", kwargs)

    # ------------------------------------------------------------------
    # Integrations: PKS (Subscription / Payment)
    # ------------------------------------------------------------------

    def get_pks_products(self) -> List[Dict[str, Any]]:
        """
        Get available subscription products from the payment service.

        Returns
        -------
        list[dict]
            Subscription tier/product objects.
        """
        return self._get("/integrations/pks/products")

    def get_pks_user_token(self) -> Dict[str, Any]:
        """Get the current user's PKS payment token."""
        return self._get("/integrations/pks/user-token")

    # ------------------------------------------------------------------
    # Misc / Utility
    # ------------------------------------------------------------------

    def get_shop_sections(self) -> List[Dict[str, Any]]:
        """Get shop/store sections."""
        return self._get("/shop/sections")

    def get_partners_shipping_cost(self, **params) -> Dict[str, Any]:
        """Get shipping cost estimates from print partners."""
        return self._get("/partners/shipping-cost", params=params)

    def get_stripe_config(self) -> Dict[str, Any]:
        """Get Stripe configuration for the current region."""
        return self._get("/integrations/stripe/config")

    def get_stripe_countries(self) -> List[Dict[str, Any]]:
        """Get countries supported by Stripe."""
        return self._get("/integrations/stripe/countries")

    def get_payment_sources(self, user_id: int) -> List[Dict[str, Any]]:
        """Get saved payment sources (cards) for a user."""
        return self._get(f"/integrations/stripe/sources/user/{user_id}")

    def get_pks_products_credits(self) -> List[Dict[str, Any]]:
        """Get credit pack products available for purchase."""
        return self._get("/integrations/pks/products/credits")


# ---------------------------------------------------------------------------
# Example usage
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    email = "your_email@example.com"
    password = "your_password"

    print("MyDesigns.io API Client - Example Usage")
    print("=" * 50)

    # Initialize client
    client = MyDesignsClient()

    # Login
    print(f"\n[1] Logging in as {email}...")
    try:
        session = client.login(email, password)
        print(f"    Logged in. Session ID: {session['id']}")
        print(f"    Expires: {session['expires_at']}")
    except Exception as e:
        print(f"    Login failed: {e}")
        sys.exit(1)

    # Get user profile
    print("\n[2] Fetching user profile...")
    try:
        me = client.get_me()
        print(f"    User: {me['name']} (ID: {me['id']})")
        print(f"    Email: {me['email']}")
        print(f"    Credits: {me['credits']}")
        print(f"    Plan: {me.get('subscriptionTier', {}).get('code', 'N/A')}")
        print(
            f"    Storage: {me.get('memoryUsed', 0) / 1e9:.1f} GB / "
            f"{me.get('memoryLimit', 0) / 1e9:.1f} GB"
        )
    except Exception as e:
        print(f"    Error: {e}")

    # Generate a Personal Access Token
    print("\n[3] Creating Personal Access Token...")
    try:
        pat = client.create_personal_access_token("example-script-token")
        print(f"    Token ID: {pat['id']}")
        print(f"    Bearer Token: {pat['bearer']}")
        print("    (Save this bearer token - it won't be shown again!)")

        # Clean up - delete the token
        client.delete_personal_access_token(pat["id"])
        print(f"    Token {pat['id']} deleted.")
    except Exception as e:
        print(f"    Error: {e}")

    # Get categories
    print("\n[4] Fetching listing categories...")
    try:
        cats = client.get_categories()
        print(f"    Found {len(cats)} categories")
        for cat in cats[:3]:
            print(f"    - [{cat['id']}] {cat['name']} ({cat['designsCount']} designs)")
    except Exception as e:
        print(f"    Error: {e}")

    # Get connected shops
    print("\n[5] Fetching connected shops...")
    try:
        providers = client.get_provider_users()
        print(f"    Connected shops: {len(providers)}")
        for p in providers[:5]:
            print(
                f"    - {p.get('providerName', 'unknown')}: "
                f"{p.get('shopName', p.get('shop', 'N/A'))}"
            )
    except Exception as e:
        print(f"    Error: {e}")

    # Get orders summary
    print("\n[6] Fetching recent orders...")
    try:
        orders = client.get_recent_orders(days_ago=30)
        print(f"    Orders in last 30 days: {len(orders)}")
    except Exception as e:
        print(f"    Error: {e}")

    # Get notifications
    print("\n[7] Fetching notifications...")
    try:
        notifications = client.get_notifications()
        unread = [n for n in notifications if not n.get("read", False)]
        print(f"    Total: {len(notifications)}, Unread: {len(unread)}")
    except Exception as e:
        print(f"    Error: {e}")

    print("\nDone!")
