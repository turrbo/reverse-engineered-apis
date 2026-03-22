# Recall.ai API Client

Unofficial Python client for **Recall.ai** (app.getrecall.ai) - an AI-powered knowledge management and recall tool.

This client was reverse-engineered from the web application's JavaScript bundle and provides programmatic access to Recall's features.

## Table of Contents

- [Features](#features)
- [Installation](#installation)
- [Authentication](#authentication)
- [Quick Start](#quick-start)
- [API Reference](#api-reference)
- [Architecture](#architecture)
- [Limitations](#limitations)

---

## Features

The client provides access to:

- **Sync API**: Push/pull data synchronization
- **Summary API**: Generate summaries from markdown, YouTube videos, Wikipedia
- **Chat API**: Ask questions about your knowledge base
- **Questions API**: Generate quiz questions with multiple-choice, explanations
- **Tags API**: Auto-generate tags for content
- **Entities API**: Extract named entities from text
- **Transcript API**: Transcribe videos, podcasts, YouTube content
- **Scraper API**: Scrape web pages and PDFs
- **Items API**: Retrieve items in reader/reference mode
- **Actions API**: Auto-format markdown content
- **PDF API**: OCR-based text extraction from PDFs
- **Cache API**: Invalidate cached content
- **Utils**: URL expansion, email validation

---

## Installation

```bash
# Clone or download the client
# No external dependencies beyond requests

pip install requests
```

Place `getrecall_client.py` in your project directory.

---

## Authentication

Recall.ai uses **Firebase Authentication** with **Google OAuth**. Since automated Google sign-in is typically blocked by CAPTCHA and 2FA, you'll need to **manually extract your authentication token** from the browser.

### Steps to Get Your Auth Token:

1. **Sign in to Recall.ai**:
   - Open https://app.getrecall.ai in your browser
   - Sign in with Google

2. **Open Developer Tools**:
   - Press `F12` (or right-click → Inspect)
   - Go to the **Application** (Chrome) or **Storage** (Firefox) tab

3. **Find Firebase Token**:
   - Navigate to **Local Storage** → `https://app.getrecall.ai`
   - Look for a key like `firebase:authUser:[project-id]:AIza...`
   - The value is a JSON object containing your auth data

4. **Extract Access Token**:
   ```json
   {
     "uid": "...",
     "email": "your-email@example.com",
     "stsTokenManager": {
       "accessToken": "eyJhbGciOiJSUzI1NiIsImtpZCI6...",  <-- Copy this
       "expirationTime": 1234567890000,
       "refreshToken": "..."
     }
   }
   ```

5. **Copy the `accessToken` value** - this is your `auth_token` for the client.

### Token Expiration

Firebase tokens typically expire after **1 hour**. When your token expires:
- You'll receive authentication errors (401/403)
- Re-extract a fresh token from your browser session
- Or implement token refresh logic using the `refreshToken`

---

## Quick Start

```python
from getrecall_client import RecallClient

# Initialize client with your auth token
client = RecallClient(auth_token="eyJhbGciOiJSUzI1NiIsImtpZCI6...")

# Pull synced cards
cards = client.sync.pull(collection="cards")
print(f"Pulled {len(cards)} cards")

# Generate a summary
summary = client.summary.summarize_markdown(
    url="https://example.com/article",
    markdown="# My Article\n\nContent here...",
    item_id="article-123",
    summary_length="detailed",
    language="en"
)
print(summary)

# Ask a question about content
answer = client.chat.ask_question(
    item_id="article-123",
    question="What are the main points?",
    url="https://example.com/article"
)
print(answer)

# Generate quiz questions
questions = client.questions.generate_questions(
    item_id="article-123",
    text="Content to generate questions from...",
    count=5,
    difficulty="mixed",
    question_types=["multiple_choice"]
)
print(questions)

# Extract entities
entities = client.entities.extract_entities(
    item_id="article-123",
    url="https://example.com/article",
    text="John Doe works at OpenAI in San Francisco."
)
print(entities)

# Generate tags
tags = client.tags.generate_tags(
    item_id="article-123",
    url="https://example.com/article",
    text="Article about machine learning and AI"
)
print(tags)

# Scrape a webpage
scraped = client.scraper.scrape_page(url="https://example.com")
print(scraped["html"])

# Transcribe YouTube video
transcript = client.transcript.scrape_youtube(
    video_id="dQw4w9WgXcQ",
    language="en"
)
print(transcript)
```

---

## API Reference

### `RecallClient(auth_token: str)`

Main client class that provides access to all API endpoints.

**Attributes:**
- `sync` - Sync API
- `summary` - Summary generation
- `chat` - Question answering
- `questions` - Quiz generation
- `tags` - Tag generation
- `entities` - Entity extraction
- `transcript` - Transcription services
- `scraper` - Web scraping
- `items` - Item retrieval
- `actions` - Content actions
- `pdf` - PDF processing
- `cache` - Cache management
- `email` - Email validation
- `utils` - Utility functions

---

### Sync API

#### `client.sync.pull(collection: str, last_pulled_at: int = None) -> List[Dict]`

Pull changes from the server.

**Parameters:**
- `collection`: Collection name (e.g., "cards", "connections", "tags")
- `last_pulled_at`: Unix timestamp of last sync (optional)

**Returns:** List of items/changes

**Example:**
```python
cards = client.sync.pull("cards")
connections = client.sync.pull("connections", last_pulled_at=1234567890)
```

#### `client.sync.push(changes: List[Dict], last_pulled_at: int = None, session_id: str = None) -> Dict`

Push changes to the server.

**Parameters:**
- `changes`: List of change objects
- `last_pulled_at`: Last pull timestamp
- `session_id`: Session identifier

**Returns:** Server response

---

### Summary API

#### `client.summary.summarize_markdown(url: str, markdown: str, item_id: str, summary_length: str = "detailed", name: str = None, language: str = "en") -> Dict`

Generate AI summary from markdown content.

**Parameters:**
- `url`: Source URL
- `markdown`: Markdown content to summarize
- `item_id`: Unique item identifier
- `summary_length`: "short", "medium", or "detailed"
- `name`: Optional title
- `language`: Language code (default: "en")

**Returns:** Summary object with text and metadata

#### `client.summary.summarize_youtube_markdown(url: str, markdown: str, item_id: str, ...) -> Dict`

Summarize YouTube video transcript.

#### `client.summary.get_summary_preview(url: str) -> Dict`

Get quick preview summary for a URL.

#### `client.summary.find_wikipedia_summary(query: str, language: str = "en") -> Dict`

Search for Wikipedia article summaries.

---

### Chat API

#### `client.chat.ask_question(item_id: str, question: str, url: str, messages: List[Dict] = None, chunks: List[Dict] = None) -> Dict`

Ask a question about specific content.

**Parameters:**
- `item_id`: Item identifier
- `question`: Question to ask
- `url`: Source URL
- `messages`: Chat history (optional)
- `chunks`: Context chunks (optional)

**Returns:** AI-generated answer

**Example:**
```python
answer = client.chat.ask_question(
    item_id="doc-123",
    question="Summarize the key findings",
    url="https://example.com/research"
)
```

#### `client.chat.ask_knowledge_base_question(question: str, messages: List[Dict] = None, chunks: List[Dict] = None) -> Dict`

Ask about your entire knowledge base.

#### `client.chat.get_chat_name(messages: List[Dict]) -> Dict`

Generate a name/title for a chat conversation.

#### `client.chat.rephrase_question(messages: List[Dict], metadata: Dict = None) -> Dict`

Rephrase a question for better search/results.

---

### Questions API

#### `client.questions.generate_questions(item_id: str, text: str, existing_questions: List[Dict] = None, count: int = 5, question_types: List[str] = None, difficulty: str = "mixed", include_explanations: bool = True, include_hints: bool = False, language: str = "en") -> Dict`

Generate quiz questions from text.

**Parameters:**
- `item_id`: Item identifier
- `text`: Text to generate questions from
- `existing_questions`: Questions to avoid duplicating
- `count`: Number of questions (default: 5)
- `question_types`: List like `["multiple_choice"]`
- `difficulty`: "easy", "medium", "hard", or "mixed"
- `include_explanations`: Include answer explanations
- `include_hints`: Include hints
- `language`: Language code

**Returns:** Generated questions with answers

**Example:**
```python
questions = client.questions.generate_questions(
    item_id="article-123",
    text="The mitochondria is the powerhouse of the cell...",
    count=3,
    difficulty="medium",
    question_types=["multiple_choice"]
)
```

---

### Tags API

#### `client.tags.generate_tags(item_id: str, url: str, text: str, existing_tags: List[str] = None, is_importing: bool = False, language: str = "en") -> Dict`

Auto-generate relevant tags for content.

**Parameters:**
- `item_id`: Item identifier
- `url`: Source URL
- `text`: Content to tag
- `existing_tags`: Existing tags to consider
- `is_importing`: Flag for bulk import
- `language`: Language code

**Returns:** Generated tags

**Example:**
```python
tags = client.tags.generate_tags(
    item_id="article-456",
    url="https://example.com",
    text="Article about machine learning and neural networks",
    existing_tags=["AI", "Technology"]
)
# Returns: ["Machine Learning", "Neural Networks", "Deep Learning", ...]
```

---

### Entities API

#### `client.entities.extract_entities(item_id: str, url: str, text: str, existing_entities: List[Dict] = None, is_importing: bool = False) -> Dict`

Extract named entities (people, places, organizations) from text.

**Parameters:**
- `item_id`: Item identifier
- `url`: Source URL
- `text`: Text to analyze
- `existing_entities`: Previously extracted entities
- `is_importing`: Import flag

**Returns:** Extracted entities with types

**Example:**
```python
entities = client.entities.extract_entities(
    item_id="doc-789",
    url="https://example.com",
    text="John Doe works at OpenAI in San Francisco."
)
# Returns: [
#   {"name": "John Doe", "type": "PERSON", ...},
#   {"name": "OpenAI", "type": "ORGANIZATION", ...},
#   {"name": "San Francisco", "type": "LOCATION", ...}
# ]
```

---

### Transcript API

#### `client.transcript.transcribe(url: str, options: Dict = None) -> Dict`

Transcribe audio/video content.

#### `client.transcript.get_podcast_transcript(url: str) -> Dict`

Get transcript for a podcast episode.

#### `client.transcript.scrape_youtube(video_id: str, language: str = "en") -> Dict`

Scrape YouTube video transcript/captions.

**Example:**
```python
transcript = client.transcript.scrape_youtube(
    video_id="dQw4w9WgXcQ",
    language="en"
)
```

---

### Scraper API

#### `client.scraper.scrape_page(url: str, method: str = "GET", data: Dict = None, headers: Dict = None, proxy_options: Dict = None, response_rules: Dict = None) -> Dict`

Scrape web page content with proxy support.

**Parameters:**
- `url`: URL to scrape
- `method`: HTTP method
- `data`: POST data
- `headers`: Custom headers
- `proxy_options`: Proxy configuration
- `response_rules`: Content processing rules

**Returns:** `{"html": "..."}` or `{"pdfFile": bytes}`

**Example:**
```python
result = client.scraper.scrape_page("https://example.com")
html_content = result["html"]
```

---

### Items API

#### `client.items.get_reader(slug: str, language: str = "en") -> Dict`

Get item in reader view (clean, formatted).

#### `client.items.get_links(slug: str, language: str = "en") -> Dict`

Get all links associated with an item.

#### `client.items.get_reference(slug: str, language: str = "en") -> Dict`

Get item in reference mode (with connections, backlinks).

---

### Actions API

#### `client.actions.auto_format(item_id: str, markdown: str, url: str = "") -> Dict`

Auto-format and clean up markdown content.

**Example:**
```python
formatted = client.actions.auto_format(
    item_id="doc-123",
    markdown="# Messy\n\n\nContent    here",
    url="https://example.com"
)
```

---

### PDF API

#### `client.pdf.extract_markdown_with_ocr(pdf_file: bytes) -> Dict`

Extract text from PDF using OCR.

**Parameters:**
- `pdf_file`: PDF file content as bytes

**Returns:** `{"text": "...", "title": "..."}`

**Example:**
```python
with open("document.pdf", "rb") as f:
    pdf_bytes = f.read()

result = client.pdf.extract_markdown_with_ocr(pdf_bytes)
print(result["text"])
print(result["title"])
```

---

### Cache API

#### `client.cache.invalidate_cache(field: str, language: str, url: str = None, markdown: str = None) -> None`

Invalidate cached summaries or content.

**Parameters:**
- `field`: Field to invalidate (e.g., "detailed_summaries", "concise_summaries")
- `language`: Language code
- `url`: Source URL
- `markdown`: Content to invalidate

---

### Utils API

#### `client.utils.expand_url(url: str) -> str`

Expand shortened URLs (bit.ly, t.co, etc.).

#### `client.email.validate(email: str) -> Dict`

Validate email address format.

---

## Architecture

### API Base URLs

Recall.ai uses multiple subdomains for different services:

```python
API_URLS = {
    "backend": "https://backend.getrecall.ai",  # General backend
    "db": "https://db.getrecall.ai",             # Primary API (sync, summaries, etc.)
    "ocr": "https://ocr.getrecall.ai",           # PDF OCR processing
    "www": "https://www.getrecall.ai"            # Marketing/public site
}
```

### Firebase Configuration

```python
FIREBASE_CONFIG = {
    "apiKey": "AIzaSyAldguaLASAFGTIqFsTAgpAovZNxb02L6Y",
    "authDomain": "app.getrecall.ai",
    "projectId": "recall-308915",
    "storageBucket": "recall-308915.appspot.com",
    "messagingSenderId": "76037267237",
    "appId": "1:76037267237:web:a859bcedcfbde2777544cc",
    "databaseURL": "https://recall-308915-default-rtdb.europe-west1.firebasedatabase.app/",
    "measurementId": "G-NR9JJSQFTF"
}
```

### Authentication Flow

1. **Google OAuth**: User signs in via Google
2. **Firebase Auth**: Google credentials are exchanged for Firebase token
3. **Access Token**: Firebase returns JWT access token (valid ~1 hour)
4. **API Requests**: All requests include `Authorization: Bearer <access_token>`

### Key Endpoints Discovered

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/sync/v1/pull` | GET | Pull synced data |
| `/sync/v1/push` | POST | Push changes |
| `/summary/markdown/` | POST | Generate summary from markdown |
| `/summary/youtube/markdown/` | POST | Summarize YouTube transcript |
| `/chat/question/v1` | POST | Ask question about item |
| `/chat/knowledge-base-question` | POST | Query knowledge base |
| `/v2/questions/generate` | POST | Generate quiz questions |
| `/v1/tags/generate` | POST | Generate tags |
| `/entities/extract/` | POST | Extract named entities |
| `/transcribe/` | POST | Transcribe media |
| `/transcribe/scrape-youtube` | GET | Get YouTube transcript |
| `/scraper/page` | POST | Scrape web page |
| `/items/reader/` | GET | Get item in reader mode |
| `/actions/auto-format` | POST | Auto-format markdown |
| `/pdf` | POST | OCR extract from PDF |
| `/cache/invalidate/` | POST | Invalidate cache |
| `/expand_url/` | GET | Expand shortened URL |
| `/email/validate/` | GET | Validate email |

---

## Limitations

### Authentication Challenges

- **Google OAuth**: Cannot be automated due to CAPTCHA and 2FA
- **Token Expiration**: Tokens expire after ~1 hour and must be refreshed
- **Manual Extraction**: Users must manually extract tokens from browser

### Rate Limiting

- Rate limits are not documented but likely exist
- No official guidance on request throttling

### API Stability

- This is an **unofficial, reverse-engineered client**
- API endpoints may change without notice
- No guarantees of backward compatibility
- Recall.ai may block or restrict access

### Feature Coverage

This client covers the **main public APIs** discovered in the JavaScript bundle. Some features may be:
- Missing (not yet discovered)
- Internal-only (not exposed to frontend)
- Deprecated or experimental

### Legal and Ethical Considerations

- This client is for **educational and personal use**
- Review Recall.ai's Terms of Service before use
- Respect rate limits and avoid abusive behavior
- Consider subscribing to Recall Plus for official API access (if/when available)

---

## Troubleshooting

### Authentication Errors (401/403)

**Problem:** Your requests return authentication errors.

**Solution:**
1. Check if your token has expired (typically 1 hour)
2. Extract a fresh token from your browser
3. Ensure you copied the entire `accessToken` value
4. Verify you're signed in to app.getrecall.ai

### Token Not Found in Browser

**Problem:** Can't find the Firebase token in localStorage.

**Solution:**
1. Make sure you're signed in to app.getrecall.ai
2. Try different storage locations:
   - Local Storage
   - Session Storage
   - IndexedDB
3. Look for keys containing "firebase" or "auth"
4. Try signing out and back in

### Connection Errors

**Problem:** Network timeouts or connection refused.

**Solution:**
1. Verify your internet connection
2. Check if Recall.ai is experiencing downtime
3. Ensure you're using the correct base URL
4. Try disabling VPN/proxy if applicable

### Invalid Response Format

**Problem:** API returns unexpected data structure.

**Solution:**
- Recall.ai may have updated their API
- Check for changes in the web app's JavaScript bundle
- File an issue or update the client code

---

## Contributing

Since this is a reverse-engineered client, contributions are welcome:

1. **Discover new endpoints**: Inspect network traffic in browser DevTools
2. **Document changes**: If APIs change, update the client
3. **Add features**: Implement missing functionality
4. **Improve auth**: Add automatic token refresh logic
5. **Share examples**: Provide usage examples

---

## Disclaimer

This is an **unofficial, reverse-engineered client** for Recall.ai. It is:
- Not affiliated with or endorsed by Recall.ai
- Provided "as-is" without warranty
- Subject to breaking changes if Recall.ai updates their API
- For educational and personal use only

Use responsibly and in accordance with Recall.ai's Terms of Service.

---

## License

MIT License - feel free to use, modify, and distribute.

---

## Changelog

### v1.0.0 (2026-03-22)
- Initial reverse-engineered client
- Comprehensive API coverage
- Firebase authentication support
- Sync, Summary, Chat, Questions, Tags, Entities, Transcript, Scraper, Items, Actions, PDF, Cache, Utils APIs

---

## Support

For issues, questions, or contributions, please open an issue on GitHub or contact the maintainer.

**Happy recalling!** 🧠✨
