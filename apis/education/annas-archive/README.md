# Anna's Archive API Client

An unofficial Python client for searching and retrieving book metadata from [Anna's Archive](https://annas-archive.gl), a search engine that aggregates books, papers, comics, magazines, and other publications from Library Genesis, Sci-Hub, Z-Library, and other sources.

## Overview

Anna's Archive is a public search engine for scholarly and general interest publications. This client provides a programmatic interface to search and retrieve metadata from the site, since no official JSON API is publicly available.

**Important Notes:**
- This is an **unofficial** client based on parsing HTML pages
- No authentication is required - all endpoints are public
- The client respects rate limits with configurable delays between requests
- This client focuses on **metadata retrieval only**, not downloading files
- Always respect copyright and use responsibly

## Features

- Search for books by title, author, ISBN, DOI, MD5, or keywords
- Filter search results by language, file format, content type
- Get detailed metadata for specific books
- ISBN and DOI lookup
- Advanced search with multiple field filters
- Pagination support
- Rate limiting to be respectful to the server
- Type hints for better IDE support

## Installation

### Requirements

- Python 3.7+
- `requests` - HTTP library
- `beautifulsoup4` - HTML parsing
- `lxml` - Fast XML/HTML parser

### Install Dependencies

```bash
# Using pip
pip install requests beautifulsoup4 lxml

# Using apt (Debian/Ubuntu)
apt-get install python3-requests python3-bs4 python3-lxml

# Using conda
conda install requests beautifulsoup4 lxml
```

## Quick Start

```python
from annas_archive_client import AnnasArchiveClient

# Initialize the client
client = AnnasArchiveClient(delay=1.5)  # 1.5 second delay between requests

# Search for books
results = client.search("Python programming", ext="pdf", lang="en")

# Display results
for book in results[:5]:
    print(f"Title: {book['title']}")
    print(f"Author: {book['author']}")
    print(f"Year: {book['year']}")
    print(f"URL: {book['url']}")
    print()

# Get detailed information about a specific book
if results:
    details = client.get_book_details(results[0]['md5'])
    print(f"Language: {details.get('language', 'N/A')}")
    print(f"File size: {details.get('file_sizes', ['N/A'])[0]}")
```

## Usage Examples

### Basic Search

```python
client = AnnasArchiveClient()

# Simple text search
results = client.search("machine learning")

# Search with pagination
page2_results = client.search("artificial intelligence", page=2)

# Search by specific fields
isbn_results = client.search("isbn:9780134853987")
doi_results = client.search("doi:10.1234/example")
```

### Filtered Search

```python
# Search for PDF books in English
results = client.search(
    "deep learning",
    ext="pdf",        # File format: pdf, epub, mobi, azw3, etc.
    lang="en"         # Language code: en, es, fr, de, etc.
)

# Filter by content type
fiction = client.search(
    "science fiction",
    content="book_fiction"
)

# Available content types:
# - book_fiction
# - book_nonfiction
# - book_unknown
# - journal_article
# - standards_document
# - magazine
# - comic_book
```

### ISBN and DOI Lookups

```python
# Search by ISBN
book = client.search_by_isbn("978-0-13-485398-7")
if book:
    print(f"Found: {book['title']}")

# Search by DOI
paper = client.search_by_doi("10.1038/nature12373")
if paper:
    print(f"Found: {paper['title']}")
```

### Advanced Search

```python
# Search with multiple specific fields
results = client.advanced_search(
    author="Martin Fowler",
    language="en",
    extension="pdf",
    year="2019"
)

# Mix field-specific and general search
results = client.advanced_search(
    title="Python",
    author="Lutz",
    extension="epub"
)
```

### Getting Book Details

```python
# Get comprehensive metadata for a book
md5 = "f87448722f0072549206b63999ec39e1"
details = client.get_book_details(md5)

print(f"Title: {details.get('title', 'N/A')}")
print(f"Language: {details.get('language', 'N/A')}")
print(f"Year: {details.get('year', 'N/A')}")
print(f"File Extensions: {details.get('file_extensions', [])}")
print(f"File Sizes: {details.get('file_sizes', [])}")

# Details may include:
# - title, author, publisher, year
# - language, isbn, doi
# - file_extensions, file_sizes
# - collection (source: zlib, libgen, ia, etc.)
# - content_type, filepath
# - Various identifiers and hashes
```

### Configuring Rate Limiting

```python
# Set custom delay between requests (in seconds)
client = AnnasArchiveClient(
    delay=2.0,      # Wait 2 seconds between requests
    timeout=60      # Request timeout in seconds
)

# For bulk operations, use longer delays
bulk_client = AnnasArchiveClient(delay=3.0)

# Process many books
book_ids = ["md5_hash_1", "md5_hash_2", "md5_hash_3"]
for md5 in book_ids:
    details = bulk_client.get_book_details(md5)
    # Process details...
```

## API Reference

### AnnasArchiveClient

#### `__init__(delay=1.0, timeout=30)`

Initialize the client.

**Parameters:**
- `delay` (float): Delay in seconds between requests (default: 1.0)
- `timeout` (int): HTTP request timeout in seconds (default: 30)

#### `search(query, page=1, content="", ext="", lang="", sort="")`

Search for books on Anna's Archive.

**Parameters:**
- `query` (str): Search query (title, author, ISBN, MD5, DOI, etc.)
- `page` (int): Page number for pagination (default: 1)
- `content` (str): Filter by content type
- `ext` (str): Filter by file extension
- `lang` (str): Filter by language code
- `sort` (str): Sort order

**Returns:** List of dictionaries with book metadata

**Example:**
```python
results = client.search("Python programming", page=1, ext="pdf", lang="en")
```

#### `get_book_details(md5)`

Get detailed information about a specific book.

**Parameters:**
- `md5` (str): The MD5 hash of the book

**Returns:** Dictionary containing detailed book metadata

**Example:**
```python
details = client.get_book_details("f87448722f0072549206b63999ec39e1")
```

#### `search_by_isbn(isbn)`

Search for a book by ISBN.

**Parameters:**
- `isbn` (str): The ISBN-10 or ISBN-13 number

**Returns:** Dictionary containing book details, or None if not found

**Example:**
```python
book = client.search_by_isbn("9780134853987")
```

#### `search_by_doi(doi)`

Search for a paper/article by DOI.

**Parameters:**
- `doi` (str): The DOI (Digital Object Identifier)

**Returns:** Dictionary containing paper details, or None if not found

**Example:**
```python
paper = client.search_by_doi("10.1234/example")
```

#### `advanced_search(title="", author="", publisher="", year="", language="", extension="", **kwargs)`

Perform an advanced search with specific field filters.

**Parameters:**
- `title` (str): Filter by title
- `author` (str): Filter by author
- `publisher` (str): Filter by publisher
- `year` (str): Filter by publication year
- `language` (str): Filter by language code
- `extension` (str): Filter by file extension
- `**kwargs`: Additional parameters passed to `search()`

**Returns:** List of book metadata dictionaries

**Example:**
```python
books = client.advanced_search(
    author="Guido van Rossum",
    extension="pdf",
    language="en"
)
```

## Data Structure

### Search Result

Each search result contains:

```python
{
    'md5': 'f87448722f0072549206b63999ec39e1',
    'title': 'Python Programming for Beginners',
    'author': 'Publishing, AMZ',
    'publisher': 'Independent Publishing',
    'year': '2021',
    'url': 'https://annas-archive.gl/md5/f87448722f0072549206b63999ec39e1'
}
```

### Book Details

Detailed book information may include:

```python
{
    'md5': 'f87448722f0072549206b63999ec39e1',
    'title': 'Python Programming for Beginners',
    'language': 'en',
    'year': '2021',
    'file_extensions': ['pdf', 'epub'],
    'file_sizes': ['5.2 MB', '3.8 MB'],
    'collection': 'zlib',
    'content_type': 'book_nonfiction',
    'isbn': '9781234567890',
    'publisher': 'Independent Publishing',
    'author': 'John Doe',
    # ... additional metadata fields
}
```

## URL Patterns

The client uses the following URL patterns:

- **Search**: `https://annas-archive.gl/search?q=query&page=1&ext=pdf&lang=en`
- **Book Details**: `https://annas-archive.gl/md5/{md5_hash}`
- **ISBN Lookup**: `https://annas-archive.gl/isbn/{isbn}` (redirects to book page)
- **DOI Lookup**: `https://annas-archive.gl/scidb/{doi}`

## Search Query Syntax

Anna's Archive supports field-specific searches:

- `title:"Python Programming"` - Search in title
- `author:"Martin Fowler"` - Search by author
- `publisher:"O'Reilly"` - Search by publisher
- `isbn:9780134853987` - Search by ISBN
- `doi:10.1234/example` - Search by DOI
- `lang:en` - Filter by language
- `year:2020` - Filter by year
- `ext:pdf` - Filter by file extension

## Language Codes

Common language codes (ISO 639-1):

- `en` - English
- `es` - Spanish
- `fr` - French
- `de` - German
- `ru` - Russian
- `zh` - Chinese
- `ja` - Japanese
- `pt` - Portuguese
- `it` - Italian
- `ar` - Arabic

## File Extensions

Supported file formats:

- `pdf` - PDF documents
- `epub` - EPUB e-books
- `mobi` - Mobipocket e-books
- `azw3` - Kindle format
- `djvu` - DjVu format
- `cbr` / `cbz` - Comic book archives
- `txt` - Plain text

## Error Handling

The client raises exceptions for network errors and parsing failures:

```python
try:
    results = client.search("test query")
    for book in results:
        try:
            details = client.get_book_details(book['md5'])
            print(details['title'])
        except Exception as e:
            print(f"Failed to get details: {e}")
except Exception as e:
    print(f"Search failed: {e}")
```

## Best Practices

1. **Respect Rate Limits**: Use appropriate delays between requests (1-2 seconds minimum)
2. **Cache Results**: Store search results locally to avoid repeated queries
3. **Error Handling**: Always wrap API calls in try-except blocks
4. **Metadata Only**: This client is for metadata retrieval - respect copyright for actual content
5. **Be Considerate**: Anna's Archive is a free service - don't overwhelm their servers

## Limitations

- HTML parsing may break if the site structure changes
- Some metadata fields may not always be available
- Search results are limited to what the website returns per page (typically 50)
- No official API means no guarantees of stability
- Rate limiting is client-side only

## Reverse Engineering Notes

This client was reverse-engineered by analyzing Anna's Archive's public web interface:

### URL Patterns Discovered

- Homepage: `https://annas-archive.gl/`
- Search endpoint: `/search?q={query}&page={page}&ext={extension}&lang={language}`
- Book detail: `/md5/{md5_hash}`
- ISBN lookup: `/isbn/{isbn}` (redirects)
- DOI lookup: `/scidb/{doi}`

### HTML Structure

Search results use:
- Book title links with class `js-vim-focus` and href `/md5/{md5}`
- Author links with `icon-[mdi--user-edit]` icon
- Publisher/year with `icon-[mdi--company]` icon

Book details page uses:
- Metadata in `<div><strong>Field:</strong> value</div>` pattern
- Language, year, and other fields in specific sections
- File information scattered throughout the page

## Contributing

This is a reverse-engineered client. If you find bugs or improvements:

1. The HTML structure may change - update the parsing logic accordingly
2. Add additional metadata fields as discovered
3. Improve error handling for edge cases
4. Add new search capabilities

## Legal and Ethical Considerations

- Anna's Archive aggregates metadata from various sources
- This client is for **metadata search and discovery only**
- Always respect copyright laws in your jurisdiction
- Support authors and publishers by purchasing books legally when possible
- Use this tool for research, discovery, and legitimate purposes only

## Troubleshooting

### No results returned

- Check your query syntax
- Try a broader search term
- Verify language and extension filters are correct
- Check if the site is accessible from your location

### Parsing errors

- The site structure may have changed
- Update the client to match new HTML patterns
- Check if you're being rate-limited

### Slow performance

- Increase the delay between requests
- Use pagination instead of fetching all results
- Cache results locally

## License

This client is provided as-is for educational and research purposes. Use responsibly.

## Disclaimer

This is an unofficial client and is not affiliated with, endorsed by, or connected to Anna's Archive in any way. The website structure may change at any time, which could break this client. Always verify data accuracy and use the official website when possible.

---

**Last Updated:** 2026-03-22
**Client Version:** 1.0
**Target Site:** annas-archive.gl
