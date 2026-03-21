#!/usr/bin/env python3
"""
Realtor.com Advanced Production Client

This is a production-ready client with:
- Proxy rotation support
- Retry logic with exponential backoff
- Rate limiting
- Caching
- Logging
- Error recovery

For high-volume scraping operations.
"""

import requests
from playwright.sync_api import sync_playwright
from typing import Dict, List, Optional, Any, Callable
import json
import time
import logging
from functools import wraps
from datetime import datetime, timedelta
import hashlib
import os
import random


class ProxyRotator:
    """Manages proxy rotation for requests."""

    def __init__(self, proxies: List[str]):
        """
        Initialize proxy rotator.

        Args:
            proxies: List of proxy URLs in format:
                     http://user:pass@host:port or http://host:port
        """
        self.proxies = proxies
        self.current_index = 0
        self.failed_proxies = set()

    def get_next(self) -> Optional[str]:
        """Get next available proxy."""
        if not self.proxies:
            return None

        attempts = 0
        while attempts < len(self.proxies):
            proxy = self.proxies[self.current_index]
            self.current_index = (self.current_index + 1) % len(self.proxies)

            if proxy not in self.failed_proxies:
                return proxy

            attempts += 1

        return None  # All proxies failed

    def mark_failed(self, proxy: str):
        """Mark a proxy as failed."""
        self.failed_proxies.add(proxy)

    def reset_failures(self):
        """Reset failed proxy tracking."""
        self.failed_proxies.clear()


class SimpleCache:
    """Simple in-memory cache with TTL."""

    def __init__(self, ttl_seconds: int = 3600):
        """
        Initialize cache.

        Args:
            ttl_seconds: Time to live for cache entries
        """
        self.cache = {}
        self.ttl = timedelta(seconds=ttl_seconds)

    def _get_key(self, *args, **kwargs) -> str:
        """Generate cache key from arguments."""
        key_data = json.dumps({'args': args, 'kwargs': kwargs}, sort_keys=True)
        return hashlib.md5(key_data.encode()).hexdigest()

    def get(self, key: str) -> Optional[Any]:
        """Get value from cache if not expired."""
        if key in self.cache:
            value, timestamp = self.cache[key]
            if datetime.now() - timestamp < self.ttl:
                return value
            else:
                del self.cache[key]
        return None

    def set(self, key: str, value: Any):
        """Set value in cache with current timestamp."""
        self.cache[key] = (value, datetime.now())

    def clear(self):
        """Clear all cache entries."""
        self.cache.clear()


def retry_with_backoff(
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    exponential_base: float = 2.0
):
    """
    Decorator for retrying functions with exponential backoff.

    Args:
        max_retries: Maximum number of retry attempts
        base_delay: Initial delay in seconds
        max_delay: Maximum delay in seconds
        exponential_base: Base for exponential backoff
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            retries = 0
            while retries < max_retries:
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    retries += 1
                    if retries >= max_retries:
                        raise

                    delay = min(base_delay * (exponential_base ** retries), max_delay)
                    # Add jitter
                    delay = delay * (0.5 + random.random())

                    logging.warning(
                        f"Attempt {retries}/{max_retries} failed: {e}. "
                        f"Retrying in {delay:.2f}s..."
                    )
                    time.sleep(delay)

            return None
        return wrapper
    return decorator


class RealtorAdvancedClient:
    """
    Production-ready Realtor.com client with advanced features.

    Features:
    - Browser automation with Playwright
    - Proxy rotation
    - Retry logic with exponential backoff
    - Rate limiting
    - Response caching
    - Comprehensive logging
    - Error recovery
    """

    def __init__(
        self,
        proxies: Optional[List[str]] = None,
        cache_ttl: int = 3600,
        rate_limit_delay: float = 2.0,
        headless: bool = False,
        log_level: str = "INFO"
    ):
        """
        Initialize advanced client.

        Args:
            proxies: List of proxy URLs (optional)
            cache_ttl: Cache TTL in seconds
            rate_limit_delay: Minimum delay between requests
            headless: Run browser in headless mode
            log_level: Logging level (DEBUG, INFO, WARNING, ERROR)
        """
        # Setup logging
        logging.basicConfig(
            level=getattr(logging, log_level),
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        self.logger = logging.getLogger(__name__)

        # Initialize components
        self.proxy_rotator = ProxyRotator(proxies) if proxies else None
        self.cache = SimpleCache(ttl_seconds=cache_ttl)
        self.rate_limit_delay = rate_limit_delay
        self.last_request_time = 0
        self.headless = headless

        # Browser components (lazy loaded)
        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None

        self.logger.info("RealtorAdvancedClient initialized")

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()

    def _ensure_browser(self):
        """Ensure browser is started."""
        if self.playwright is None:
            self.logger.info("Starting browser session...")
            self.playwright = sync_playwright().start()

            launch_options = {
                'headless': self.headless,
                'args': [
                    '--disable-blink-features=AutomationControlled',
                    '--disable-dev-shm-usage',
                    '--no-sandbox'
                ]
            }

            # Add proxy if available
            if self.proxy_rotator:
                proxy = self.proxy_rotator.get_next()
                if proxy:
                    self.logger.info(f"Using proxy: {proxy}")
                    launch_options['proxy'] = {'server': proxy}

            self.browser = self.playwright.chromium.launch(**launch_options)

            self.context = self.browser.new_context(
                viewport={'width': 1920, 'height': 1080},
                user_agent=(
                    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                    'AppleWebKit/537.36 (KHTML, like Gecko) '
                    'Chrome/120.0.0.0 Safari/537.36'
                ),
            )

            self.context.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined
                });
            """)

            self.page = self.context.new_page()
            self.logger.info("Browser session started successfully")

    def _rate_limit(self):
        """Apply rate limiting delay."""
        elapsed = time.time() - self.last_request_time
        if elapsed < self.rate_limit_delay:
            sleep_time = self.rate_limit_delay - elapsed
            self.logger.debug(f"Rate limiting: sleeping {sleep_time:.2f}s")
            time.sleep(sleep_time)
        self.last_request_time = time.time()

    @retry_with_backoff(max_retries=3, base_delay=2.0)
    def search_properties(
        self,
        location: str,
        **filters
    ) -> List[Dict[str, Any]]:
        """
        Search for properties with caching and retry logic.

        Args:
            location: City, state, or ZIP code
            **filters: Additional filters (beds_min, price_max, etc.)

        Returns:
            List of property dictionaries
        """
        # Check cache
        cache_key = self.cache._get_key('search', location, **filters)
        cached_result = self.cache.get(cache_key)
        if cached_result:
            self.logger.info(f"Cache hit for search: {location}")
            return cached_result

        self.logger.info(f"Searching properties in: {location}")

        # Apply rate limiting
        self._rate_limit()

        # Ensure browser is ready
        self._ensure_browser()

        # Build URL
        location_slug = location.lower().replace(' ', '-').replace(',', '')
        url = f"https://www.realtor.com/realestateandhomes-search/{location_slug}"

        # Navigate
        try:
            self.page.goto(url, timeout=30000)
            self.page.wait_for_load_state('networkidle')

            # Wait for content
            try:
                self.page.wait_for_selector('[data-testid="property-card"]', timeout=10000)
            except:
                pass

            # Extract properties
            properties = self._extract_properties()

            # Apply filters
            filtered = self._apply_client_side_filters(properties, **filters)

            # Cache results
            self.cache.set(cache_key, filtered)

            self.logger.info(f"Found {len(filtered)} properties")
            return filtered

        except Exception as e:
            self.logger.error(f"Error searching properties: {e}")
            raise

    def _extract_properties(self) -> List[Dict[str, Any]]:
        """Extract property data from current page."""
        properties = []

        cards = self.page.query_selector_all('[data-testid="property-card"]')
        self.logger.debug(f"Found {len(cards)} property cards")

        for idx, card in enumerate(cards):
            try:
                prop = {
                    'extracted_at': datetime.now().isoformat(),
                }

                # Address
                addr = card.query_selector('[data-testid="property-address"]')
                if addr:
                    prop['address'] = addr.inner_text().strip()

                # Price
                price = card.query_selector('[data-testid="property-price"]')
                if price:
                    price_text = price.inner_text().strip()
                    prop['price_raw'] = price_text
                    prop['price'] = self._parse_price(price_text)

                # Beds
                beds = card.query_selector('[data-testid="property-bed"]')
                if beds:
                    prop['beds'] = self._parse_number(beds.inner_text())

                # Baths
                baths = card.query_selector('[data-testid="property-bath"]')
                if baths:
                    prop['baths'] = self._parse_number(baths.inner_text())

                # Sqft
                sqft = card.query_selector('[data-testid="property-sqft"]')
                if sqft:
                    prop['sqft'] = self._parse_number(sqft.inner_text())

                # URL
                link = card.query_selector('a')
                if link:
                    href = link.get_attribute('href')
                    if href:
                        prop['url'] = f"https://www.realtor.com{href}" if href.startswith('/') else href

                if 'address' in prop or 'price' in prop:
                    properties.append(prop)

            except Exception as e:
                self.logger.warning(f"Error extracting property {idx}: {e}")
                continue

        return properties

    def _apply_client_side_filters(
        self,
        properties: List[Dict],
        beds_min: Optional[int] = None,
        baths_min: Optional[int] = None,
        price_min: Optional[int] = None,
        price_max: Optional[int] = None,
        **kwargs
    ) -> List[Dict]:
        """Apply filters to property list."""
        filtered = properties

        if beds_min:
            filtered = [p for p in filtered if p.get('beds', 0) >= beds_min]

        if baths_min:
            filtered = [p for p in filtered if p.get('baths', 0) >= baths_min]

        if price_min:
            filtered = [p for p in filtered if p.get('price', 0) >= price_min]

        if price_max:
            filtered = [p for p in filtered if p.get('price', float('inf')) <= price_max]

        return filtered

    @staticmethod
    def _parse_price(text: str) -> Optional[int]:
        """Parse price from text."""
        if not text:
            return None

        text = text.replace('$', '').replace(',', '').strip()

        multiplier = 1
        if 'M' in text or 'm' in text:
            multiplier = 1_000_000
            text = text.replace('M', '').replace('m', '')
        elif 'K' in text or 'k' in text:
            multiplier = 1_000
            text = text.replace('K', '').replace('k', '')

        try:
            return int(float(text) * multiplier)
        except:
            return None

    @staticmethod
    def _parse_number(text: str) -> Optional[int]:
        """Parse number from text."""
        import re
        if not text:
            return None

        match = re.search(r'([\d,]+)', text)
        if match:
            try:
                return int(match.group(1).replace(',', ''))
            except:
                return None
        return None

    def export_to_json(self, properties: List[Dict], filename: str):
        """Export properties to JSON file."""
        with open(filename, 'w') as f:
            json.dump(properties, f, indent=2)
        self.logger.info(f"Exported {len(properties)} properties to {filename}")

    def export_to_csv(self, properties: List[Dict], filename: str):
        """Export properties to CSV file."""
        import csv

        if not properties:
            self.logger.warning("No properties to export")
            return

        keys = set()
        for prop in properties:
            keys.update(prop.keys())

        with open(filename, 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=sorted(keys))
            writer.writeheader()
            writer.writerows(properties)

        self.logger.info(f"Exported {len(properties)} properties to {filename}")

    def get_stats(self) -> Dict[str, Any]:
        """Get client statistics."""
        return {
            'cache_size': len(self.cache.cache),
            'proxies_available': len(self.proxy_rotator.proxies) if self.proxy_rotator else 0,
            'proxies_failed': len(self.proxy_rotator.failed_proxies) if self.proxy_rotator else 0,
        }

    def close(self):
        """Close browser and cleanup."""
        self.logger.info("Closing client...")

        if self.page:
            self.page.close()
        if self.context:
            self.context.close()
        if self.browser:
            self.browser.close()
        if self.playwright:
            self.playwright.stop()

        self.logger.info("Client closed")


if __name__ == "__main__":
    """Example usage."""

    print("=" * 70)
    print("Realtor.com Advanced Production Client")
    print("=" * 70)

    # Example 1: Basic usage
    print("\n[Example 1] Basic search")
    with RealtorAdvancedClient(rate_limit_delay=2.0, log_level="INFO") as client:
        properties = client.search_properties(
            location="Miami, FL",
            beds_min=3,
            price_max=1_000_000
        )

        print(f"\nFound {len(properties)} properties")

        for i, prop in enumerate(properties[:3], 1):
            print(f"\n  [{i}] {prop.get('address', 'N/A')}")
            print(f"      Price: ${prop.get('price', 0):,}")
            print(f"      Beds/Baths: {prop.get('beds', '?')}/{prop.get('baths', '?')}")

        # Export results
        client.export_to_json(properties, '/tmp/realtor_results.json')
        print(f"\n✓ Exported to /tmp/realtor_results.json")

        # Show stats
        stats = client.get_stats()
        print(f"\nClient stats: {stats}")

    # Example 2: With proxy rotation (if you have proxies)
    print("\n" + "=" * 70)
    print("[Example 2] With proxy rotation (commented out)")
    print("=" * 70)
    print("""
# Uncomment to use proxies:
proxies = [
    'http://user:pass@proxy1.example.com:8080',
    'http://user:pass@proxy2.example.com:8080',
]

with RealtorAdvancedClient(proxies=proxies) as client:
    properties = client.search_properties("Los Angeles, CA")
    """)

    print("\n" + "=" * 70)
    print("Advanced client features:")
    print("  ✓ Automatic retries with exponential backoff")
    print("  ✓ Response caching (1 hour TTL)")
    print("  ✓ Rate limiting (2 second default delay)")
    print("  ✓ Proxy rotation support")
    print("  ✓ Comprehensive logging")
    print("  ✓ CSV/JSON export")
    print("  ✓ Error recovery")
    print("=" * 70)
