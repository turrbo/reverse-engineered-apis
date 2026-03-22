"""
Anna's Archive API Client

A Python client for searching and retrieving book metadata from Anna's Archive (annas-archive.gl).
This is an unofficial client that parses the public HTML pages since there is no official JSON API.

Anna's Archive is a search engine for books, papers, comics, magazines, and other publications,
aggregating metadata from Library Genesis, Sci-Hub, Z-Library, and other sources.

Author: Reverse engineered API client
Date: 2026-03-22
"""

import re
import time
from typing import List, Dict, Optional, Any
from urllib.parse import urljoin, urlencode, quote_plus

import requests
from bs4 import BeautifulSoup


class AnnasArchiveClient:
    """
    Client for interacting with Anna's Archive search engine.

    This client provides methods to:
    - Search for books by title, author, ISBN, DOI, MD5
    - Get detailed book information
    - Lookup books by ISBN
    - Parse metadata from search results

    Note: This client respects rate limits and includes delays between requests.
    """

    BASE_URL = "https://annas-archive.gl"

    def __init__(self, delay: float = 1.0, timeout: int = 30):
        """
        Initialize the Anna's Archive client.

        Args:
            delay: Delay in seconds between requests (default: 1.0)
            timeout: Request timeout in seconds (default: 30)
        """
        self.delay = delay
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate',
            'DNT': '1',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1'
        })
        self.last_request_time = 0

    def _rate_limit(self):
        """Enforce rate limiting between requests."""
        elapsed = time.time() - self.last_request_time
        if elapsed < self.delay:
            time.sleep(self.delay - elapsed)
        self.last_request_time = time.time()

    def _make_request(self, url: str) -> BeautifulSoup:
        """
        Make an HTTP request with rate limiting and error handling.

        Args:
            url: The URL to request

        Returns:
            BeautifulSoup object containing parsed HTML

        Raises:
            requests.RequestException: If the request fails
        """
        self._rate_limit()

        try:
            response = self.session.get(url, timeout=self.timeout)
            response.raise_for_status()
            return BeautifulSoup(response.content, 'lxml')
        except requests.RequestException as e:
            raise Exception(f"Request failed for {url}: {str(e)}")

    def search(
        self,
        query: str,
        page: int = 1,
        content: str = "",
        ext: str = "",
        lang: str = "",
        sort: str = ""
    ) -> List[Dict[str, Any]]:
        """
        Search for books on Anna's Archive.

        Args:
            query: Search query (title, author, ISBN, MD5, DOI, etc.)
            page: Page number (default: 1)
            content: Filter by content type (e.g., 'book_fiction', 'book_nonfiction', 'journal_article')
            ext: Filter by file extension (e.g., 'pdf', 'epub', 'mobi')
            lang: Filter by language code (e.g., 'en', 'es', 'fr')
            sort: Sort order (e.g., '', 'newest', 'oldest')

        Returns:
            List of dictionaries containing book metadata

        Example:
            >>> client = AnnasArchiveClient()
            >>> results = client.search("Python programming", page=1, ext="pdf", lang="en")
            >>> for book in results:
            ...     print(f"{book['title']} by {book['author']}")
        """
        params = {'q': query}

        if page > 1:
            params['page'] = page
        if content:
            params['content'] = content
        if ext:
            params['ext'] = ext
        if lang:
            params['lang'] = lang
        if sort:
            params['sort'] = sort

        search_url = f"{self.BASE_URL}/search?{urlencode(params)}"
        soup = self._make_request(search_url)

        return self._parse_search_results(soup)

    def _parse_search_results(self, soup: BeautifulSoup) -> List[Dict[str, Any]]:
        """
        Parse search results from HTML.

        Args:
            soup: BeautifulSoup object containing search results page

        Returns:
            List of book metadata dictionaries
        """
        results = []

        # Find all book title links (they have the js-vim-focus class)
        book_links = soup.find_all('a', class_='js-vim-focus')

        for link in book_links:
            try:
                # Extract MD5 and title
                href = link.get('href', '')
                if '/md5/' not in href:
                    continue

                md5 = href.split('/md5/')[1]
                title = link.get_text(strip=True)

                # Find parent container for additional metadata
                parent = link.find_parent('div', class_=True)

                author = None
                publisher = None
                year = None

                if parent:
                    # Look for author (has user-edit icon)
                    author_links = parent.find_all('a', href=lambda x: x and '/search?q=' in x)

                    # First pass: identify author vs publisher/year
                    for idx, al in enumerate(author_links):
                        parent_html = str(al.parent) if al.parent else ""
                        text = al.get_text(strip=True)

                        if 'icon-[mdi--user-edit]' in parent_html:
                            # This is the author
                            author = text
                        elif 'icon-[mdi--company]' in parent_html:
                            # This is publisher and/or year
                            # Try to split publisher and year
                            parts = text.rsplit(',', 1)
                            if len(parts) == 2:
                                publisher = parts[0].strip()
                                year_match = re.search(r'\d{4}', parts[1])
                                if year_match:
                                    year = year_match.group(0)
                            else:
                                # Check if it's just a year
                                year_match = re.search(r'^\d{4}$', text)
                                if year_match:
                                    year = text
                                else:
                                    publisher = text
                        elif idx == 1 and not author:
                            # Sometimes the second link is author even without the icon
                            author = text

                results.append({
                    'md5': md5,
                    'title': title,
                    'author': author,
                    'publisher': publisher,
                    'year': year,
                    'url': f"{self.BASE_URL}/md5/{md5}"
                })

            except Exception as e:
                # Skip problematic entries
                continue

        return results

    def get_book_details(self, md5: str) -> Dict[str, Any]:
        """
        Get detailed information about a specific book.

        Args:
            md5: The MD5 hash of the book

        Returns:
            Dictionary containing detailed book metadata

        Example:
            >>> client = AnnasArchiveClient()
            >>> details = client.get_book_details("f87448722f0072549206b63999ec39e1")
            >>> print(details['title'])
        """
        detail_url = f"{self.BASE_URL}/md5/{md5}"
        soup = self._make_request(detail_url)

        return self._parse_book_details(soup, md5)

    def _parse_book_details(self, soup: BeautifulSoup, md5: str) -> Dict[str, Any]:
        """
        Parse detailed book information from HTML.

        Args:
            soup: BeautifulSoup object containing book detail page
            md5: The MD5 hash of the book

        Returns:
            Dictionary containing book metadata
        """
        details = {'md5': md5}

        # Extract title (usually in a large font div)
        title_div = soup.find('div', class_=lambda x: x and 'text-3xl' in x and 'font-bold' in x)
        if title_div:
            details['title'] = title_div.get_text(strip=True)

        # Extract metadata from <strong> tags
        for div in soup.find_all('div'):
            strong = div.find('strong')
            if strong:
                field_name = strong.get_text(strip=True).rstrip(':')

                # Get the value after the strong tag
                value_text = div.get_text(strip=True)
                value_text = value_text.replace(strong.get_text(strip=True), '').strip()

                # Clean up common artifacts
                value_text = re.sub(r'copy.*?copied!', '', value_text, flags=re.IGNORECASE)
                value_text = value_text.split('AA:')[0].strip()  # Remove "Search Anna's Archive" links
                value_text = value_text.split('Codes Explorer:')[0].strip()
                value_text = value_text.split('Website:')[0].strip()

                if value_text and len(value_text) < 500:
                    field_key = field_name.lower().replace(' ', '_')
                    details[field_key] = value_text

        # Look for file extension and size
        file_extensions = []
        file_sizes = []

        for text in soup.stripped_strings:
            # Look for file extensions
            ext_match = re.search(r'\b(pdf|epub|mobi|azw3|djvu|cbr|cbz)\b', text, re.I)
            if ext_match:
                ext = ext_match.group(1).lower()
                if ext not in file_extensions:
                    file_extensions.append(ext)

            # Look for file sizes
            size_match = re.search(r'(\d+(?:\.\d+)?)\s*(KB|MB|GB)', text, re.I)
            if size_match:
                size = f"{size_match.group(1)} {size_match.group(2).upper()}"
                if size not in file_sizes:
                    file_sizes.append(size)

        if file_extensions:
            details['file_extensions'] = file_extensions
        if file_sizes:
            details['file_sizes'] = file_sizes

        return details

    def search_by_isbn(self, isbn: str) -> Optional[Dict[str, Any]]:
        """
        Search for a book by ISBN.

        Args:
            isbn: The ISBN-10 or ISBN-13 number

        Returns:
            Dictionary containing book details, or None if not found

        Example:
            >>> client = AnnasArchiveClient()
            >>> book = client.search_by_isbn("9780134853987")
            >>> if book:
            ...     print(book['title'])
        """
        # Clean ISBN (remove hyphens and spaces)
        isbn_clean = re.sub(r'[^0-9X]', '', isbn.upper())

        # Try direct ISBN lookup (it redirects to the actual page)
        try:
            isbn_url = f"{self.BASE_URL}/isbn/{isbn_clean}"
            response = self.session.get(isbn_url, timeout=self.timeout, allow_redirects=True)

            if response.status_code == 200:
                soup = BeautifulSoup(response.content, 'lxml')

                # Check if we were redirected to a book detail page
                if '/md5/' in response.url:
                    md5 = response.url.split('/md5/')[1].split('/')[0]
                    return self._parse_book_details(soup, md5)
                elif '/isbndb/' in response.url:
                    # Parse ISBN database page
                    return self._parse_book_details(soup, isbn_clean)

            # Fallback to regular search
            results = self.search(f"isbn:{isbn_clean}")
            return results[0] if results else None

        except Exception as e:
            # Fallback to regular search
            results = self.search(f"isbn:{isbn_clean}")
            return results[0] if results else None

    def search_by_doi(self, doi: str) -> Optional[Dict[str, Any]]:
        """
        Search for a paper/article by DOI.

        Args:
            doi: The DOI (Digital Object Identifier)

        Returns:
            Dictionary containing paper details, or None if not found

        Example:
            >>> client = AnnasArchiveClient()
            >>> paper = client.search_by_doi("10.1234/example")
        """
        results = self.search(f"doi:{doi}")
        return results[0] if results else None

    def advanced_search(
        self,
        title: str = "",
        author: str = "",
        publisher: str = "",
        year: str = "",
        language: str = "",
        extension: str = "",
        **kwargs
    ) -> List[Dict[str, Any]]:
        """
        Perform an advanced search with specific field filters.

        Args:
            title: Filter by title
            author: Filter by author
            publisher: Filter by publisher
            year: Filter by publication year
            language: Filter by language code
            extension: Filter by file extension
            **kwargs: Additional parameters passed to search()

        Returns:
            List of book metadata dictionaries

        Example:
            >>> client = AnnasArchiveClient()
            >>> books = client.advanced_search(
            ...     author="Guido van Rossum",
            ...     extension="pdf",
            ...     language="en"
            ... )
        """
        query_parts = []

        if title:
            query_parts.append(f'title:"{title}"')
        if author:
            query_parts.append(f'author:"{author}"')
        if publisher:
            query_parts.append(f'publisher:"{publisher}"')
        if year:
            query_parts.append(f'year:{year}')
        if language:
            kwargs['lang'] = language
        if extension:
            kwargs['ext'] = extension

        query = ' '.join(query_parts) if query_parts else ""

        if not query and not kwargs:
            raise ValueError("At least one search parameter must be provided")

        return self.search(query, **kwargs)


def main():
    """
    Example usage of the AnnasArchiveClient.
    """
    print("Anna's Archive API Client - Example Usage")
    print("=" * 60)

    # Initialize client
    client = AnnasArchiveClient(delay=1.5)  # 1.5 second delay between requests

    # Example 1: Basic search
    print("\n1. Searching for 'Python programming'...")
    try:
        results = client.search("Python programming", page=1)
        print(f"Found {len(results)} results on page 1\n")

        for i, book in enumerate(results[:3], 1):
            print(f"{i}. {book['title'][:70]}")
            if book['author']:
                print(f"   Author: {book['author']}")
            if book['publisher']:
                print(f"   Publisher: {book['publisher']}")
            if book['year']:
                print(f"   Year: {book['year']}")
            print(f"   MD5: {book['md5']}")
            print()
    except Exception as e:
        print(f"Error during search: {e}\n")

    # Example 2: Search with filters
    print("\n2. Searching for PDF books in English...")
    try:
        results = client.search("machine learning", ext="pdf", lang="en")
        print(f"Found {len(results)} results\n")

        if results:
            book = results[0]
            print(f"First result: {book['title'][:70]}")
            print(f"Author: {book.get('author', 'N/A')}")
            print()
    except Exception as e:
        print(f"Error during filtered search: {e}\n")

    # Example 3: Get book details
    print("\n3. Getting detailed information for a specific book...")
    try:
        if results:
            md5 = results[0]['md5']
            details = client.get_book_details(md5)

            print("Book Details:")
            for key, value in details.items():
                if value and key != 'md5':
                    print(f"  {key}: {value}")
            print()
    except Exception as e:
        print(f"Error getting book details: {e}\n")

    # Example 4: ISBN search
    print("\n4. Searching by ISBN...")
    try:
        # Using a common ISBN for testing
        book = client.search_by_isbn("9780134853987")
        if book:
            print(f"Found book: {book.get('title', 'N/A')}")
        else:
            print("Book not found")
    except Exception as e:
        print(f"Error during ISBN search: {e}")

    # Example 5: Advanced search
    print("\n5. Advanced search with multiple criteria...")
    try:
        books = client.advanced_search(
            author="Martin",
            language="en",
            extension="pdf"
        )
        print(f"Found {len(books)} books by authors named Martin in PDF format")
        if books:
            print(f"First result: {books[0]['title'][:70]}")
    except Exception as e:
        print(f"Error during advanced search: {e}")

    print("\n" + "=" * 60)
    print("Examples completed!")


if __name__ == "__main__":
    main()
