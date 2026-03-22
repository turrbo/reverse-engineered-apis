"""
Recall.ai API Client
--------------------
Unofficial Python client for the Recall.ai (app.getrecall.ai) API.

This client was reverse-engineered from the web application's JavaScript bundle.
It provides access to Recall's knowledge management and AI features.

Authentication:
--------------
Since Recall uses Google OAuth with Firebase, you'll need to manually extract
your authentication token from the browser:

1. Open https://app.getrecall.ai in your browser and sign in
2. Open Developer Tools (F12)
3. Go to the Application/Storage tab
4. Find localStorage or sessionStorage
5. Look for a Firebase token (usually under a key like 'firebase:authUser')
6. Extract the 'stsTokenManager.accessToken' value

Usage:
------
    from getrecall_client import RecallClient

    # Initialize with your auth token
    client = RecallClient(auth_token="your_firebase_token_here")

    # Use the API
    items = client.sync.pull(collection="cards")
    summary = client.summary.summarize_markdown(
        url="https://example.com",
        markdown="# Content here",
        item_id="some-id",
        summary_length="detailed"
    )
"""

import json
import base64
from typing import Dict, List, Optional, Any, Literal
from dataclasses import dataclass
from urllib.parse import urlencode
import requests


# Firebase Configuration (from the bundle)
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

# API Base URLs
API_URLS = {
    "backend": "https://backend.getrecall.ai",
    "db": "https://db.getrecall.ai",
    "ocr": "https://ocr.getrecall.ai",
    "www": "https://www.getrecall.ai"
}


class RecallAPIError(Exception):
    """Base exception for Recall API errors"""
    pass


class RecallAuthError(RecallAPIError):
    """Authentication-related errors"""
    pass


class RecallHTTPClient:
    """Base HTTP client with authentication"""

    def __init__(self, auth_token: str, base_url: str = API_URLS["db"]):
        self.auth_token = auth_token
        self.base_url = base_url.rstrip('/')
        self.session = requests.Session()

    def _get_headers(self, content_type: str = "application/json",
                     is_importing: bool = False) -> Dict[str, str]:
        """Get HTTP headers including auth"""
        headers = {
            "Authorization": f"Bearer {self.auth_token}",
            "Content-Type": content_type,
        }
        if is_importing:
            headers["Is-Importing"] = "true"
        return headers

    def _build_url(self, path: str, query_params: Optional[Dict[str, Any]] = None) -> str:
        """Build complete URL with query parameters"""
        # Filter out None values
        if query_params:
            query_params = {k: v for k, v in query_params.items() if v is not None}

        url = f"{self.base_url}{path}"
        if query_params:
            url += f"?{urlencode(query_params)}"
        return url

    def get(self, path: str, query_params: Optional[Dict[str, Any]] = None) -> requests.Response:
        """Make GET request"""
        url = self._build_url(path, query_params)
        response = self.session.get(url, headers=self._get_headers())
        response.raise_for_status()
        return response

    def post(self, path: str, data: Any = None,
             query_params: Optional[Dict[str, Any]] = None,
             is_importing: bool = False,
             content_type: str = "application/json") -> requests.Response:
        """Make POST request"""
        url = self._build_url(path, query_params)
        headers = self._get_headers(content_type, is_importing)

        if isinstance(data, dict):
            data = json.dumps(data)

        response = self.session.post(url, data=data, headers=headers)
        response.raise_for_status()
        return response


class SyncAPI:
    """Sync API for push/pull operations"""

    def __init__(self, client: RecallHTTPClient):
        self.client = client

    def pull(self, collection: str, last_pulled_at: Optional[int] = None) -> List[Dict]:
        """
        Pull changes from the server

        Args:
            collection: Collection name (e.g., "cards", "connections")
            last_pulled_at: Timestamp of last sync (optional)

        Returns:
            List of changes/items
        """
        query_params = {"collection": collection}
        if last_pulled_at:
            query_params["lastPulledAt"] = last_pulled_at

        response = self.client.get("/sync/v1/pull", query_params)
        return response.json()

    def push(self, changes: List[Dict], last_pulled_at: Optional[int] = None,
             session_id: Optional[str] = None) -> Dict:
        """
        Push changes to the server

        Args:
            changes: List of changes to push
            last_pulled_at: Timestamp of last pull
            session_id: Session identifier

        Returns:
            Server response
        """
        data = {
            "changes": changes,
            "lastPulledAt": last_pulled_at,
            "sessionId": session_id
        }
        response = self.client.post("/sync/v1/push", data)
        return response.json()


class SummaryAPI:
    """Summary generation API"""

    def __init__(self, client: RecallHTTPClient):
        self.client = client

    def summarize_markdown(self, url: str, markdown: str, item_id: str,
                          summary_length: Literal["short", "medium", "detailed"] = "detailed",
                          name: Optional[str] = None,
                          language: str = "en") -> Dict:
        """
        Generate summary from markdown content

        Args:
            url: Source URL
            markdown: Markdown content to summarize
            item_id: Item identifier
            summary_length: Length of summary (short/medium/detailed)
            name: Optional name for the summary
            language: Language code (default: en)

        Returns:
            Summary object
        """
        query_params = {"url": url, "itemId": item_id}
        data = {
            "url": url,
            "markdown": markdown,
            "summaryLength": summary_length,
            "name": name,
            "language": language
        }
        response = self.client.post("/summary/markdown/", data, query_params)
        return response.json()

    def summarize_youtube_markdown(self, url: str, markdown: str, item_id: str,
                                   summary_length: Literal["short", "medium", "detailed"] = "detailed",
                                   name: Optional[str] = None,
                                   language: str = "en") -> Dict:
        """Generate summary from YouTube video transcript"""
        query_params = {"url": url, "itemId": item_id}
        data = {
            "url": url,
            "markdown": markdown,
            "summaryLength": summary_length,
            "name": name,
            "language": language
        }
        response = self.client.post("/summary/youtube/markdown/", data, query_params)
        return response.json()

    def get_summary_preview(self, url: str) -> Dict:
        """Get preview summary for a URL"""
        response = self.client.get("/search-preview/", {"url": url})
        return response.json()

    def find_wikipedia_summary(self, query: str, language: str = "en") -> Dict:
        """Search for Wikipedia summaries"""
        response = self.client.get("/items/search", {"query": query, "language": language})
        return response.json()


class ChatAPI:
    """Chat/Question-answering API"""

    def __init__(self, client: RecallHTTPClient):
        self.client = client

    def ask_question(self, item_id: str, question: str, url: str,
                    messages: Optional[List[Dict]] = None,
                    chunks: Optional[List[Dict]] = None) -> Dict:
        """
        Ask a question about a specific item

        Args:
            item_id: Item identifier
            question: Question to ask
            url: Source URL
            messages: Chat history
            chunks: Context chunks

        Returns:
            AI response
        """
        query_params = {"itemId": item_id, "url": url}
        data = {
            "question": question,
            "messages": messages or [],
            "chunks": chunks or []
        }
        response = self.client.post("/chat/question/v1", data, query_params)
        return response.json()

    def ask_knowledge_base_question(self, question: str,
                                   messages: Optional[List[Dict]] = None,
                                   chunks: Optional[List[Dict]] = None) -> Dict:
        """Ask a question about the knowledge base"""
        data = {
            "question": question,
            "messages": messages or [],
            "chunks": chunks or []
        }
        response = self.client.post("/chat/knowledge-base-question", data)
        return response.json()

    def get_chat_name(self, messages: List[Dict]) -> Dict:
        """Generate a name for a chat conversation"""
        response = self.client.post("/chat/name", {"messages": messages})
        return response.json()

    def rephrase_question(self, messages: List[Dict], metadata: Optional[Dict] = None) -> Dict:
        """Rephrase a question for better results"""
        data = {"messages": messages, "metadata": metadata or {}}
        response = self.client.post("/chat/rephrase", data)
        return response.json()


class QuestionsAPI:
    """Questions/Quiz generation API"""

    def __init__(self, client: RecallHTTPClient):
        self.client = client

    def generate_questions(self, item_id: str, text: str,
                          existing_questions: Optional[List[Dict]] = None,
                          count: int = 5,
                          question_types: Optional[List[str]] = None,
                          difficulty: Literal["easy", "medium", "hard", "mixed"] = "mixed",
                          include_explanations: bool = True,
                          include_hints: bool = False,
                          language: str = "en") -> Dict:
        """
        Generate quiz questions from text

        Args:
            item_id: Item identifier
            text: Text to generate questions from
            existing_questions: Questions to avoid duplicating
            count: Number of questions to generate
            question_types: Types of questions (e.g., ["multiple_choice"])
            difficulty: Question difficulty level
            include_explanations: Include explanations for answers
            include_hints: Include hints
            language: Language code

        Returns:
            Generated questions
        """
        query_params = {"itemId": item_id}
        data = {
            "text": text,
            "existing_questions": existing_questions,
            "count": count,
            "question_types": question_types or ["multiple_choice"],
            "difficulty": difficulty,
            "include_explanations": include_explanations,
            "include_hints": include_hints,
            "language": language
        }
        response = self.client.post("/v2/questions/generate", data, query_params)
        return response.json()


class TagsAPI:
    """Tag generation API"""

    def __init__(self, client: RecallHTTPClient):
        self.client = client

    def generate_tags(self, item_id: str, url: str, text: str,
                     existing_tags: Optional[List[str]] = None,
                     is_importing: bool = False,
                     language: str = "en") -> Dict:
        """
        Generate tags for content

        Args:
            item_id: Item identifier
            url: Source URL
            text: Text to generate tags from
            existing_tags: Existing tags to consider
            is_importing: Whether this is an import operation
            language: Language code

        Returns:
            Generated tags
        """
        query_params = {"itemId": item_id, "url": url}
        data = {
            "text": text,
            "tags": existing_tags or [],
            "language": language
        }
        response = self.client.post("/v1/tags/generate", data, query_params,
                                    is_importing=is_importing)
        return response.json()


class EntitiesAPI:
    """Entity extraction API"""

    def __init__(self, client: RecallHTTPClient):
        self.client = client

    def extract_entities(self, item_id: str, url: str, text: str,
                        existing_entities: Optional[List[Dict]] = None,
                        is_importing: bool = False) -> Dict:
        """
        Extract named entities from text

        Args:
            item_id: Item identifier
            url: Source URL
            text: Text to extract entities from
            existing_entities: Existing entities to consider
            is_importing: Whether this is an import operation

        Returns:
            Extracted entities
        """
        query_params = {"itemId": item_id, "url": url}
        data = {
            "text": text,
            "existingEntities": existing_entities or []
        }
        response = self.client.post("/entities/extract/", data, query_params,
                                    is_importing=is_importing)
        return response.json()


class TranscriptAPI:
    """Transcript/transcription API"""

    def __init__(self, client: RecallHTTPClient):
        self.client = client

    def transcribe(self, url: str, options: Optional[Dict] = None) -> Dict:
        """
        Transcribe audio/video content

        Args:
            url: URL of media to transcribe
            options: Additional transcription options

        Returns:
            Transcript data
        """
        data = {"url": url, **(options or {})}
        response = self.client.post("/transcribe/", data, {"url": url})
        return response.json()

    def get_podcast_transcript(self, url: str) -> Optional[Dict]:
        """Get transcript for a podcast"""
        try:
            response = self.client.post("/transcribe/podcast", {"url": url})
            return response.json()
        except Exception:
            return None

    def scrape_youtube(self, video_id: str, language: str = "en") -> Optional[Dict]:
        """Scrape YouTube video transcript"""
        try:
            response = self.client.get("/transcribe/scrape-youtube",
                                      {"video_id": video_id, "language": language})
            return response.json()
        except Exception:
            return None


class ScraperAPI:
    """Web scraping API"""

    def __init__(self, client: RecallHTTPClient):
        self.client = client

    def scrape_page(self, url: str, method: str = "GET",
                   data: Optional[Dict] = None,
                   headers: Optional[Dict] = None,
                   proxy_options: Optional[Dict] = None,
                   response_rules: Optional[Dict] = None) -> Dict:
        """
        Scrape a web page

        Args:
            url: URL to scrape
            method: HTTP method
            data: Request data
            headers: Request headers
            proxy_options: Proxy configuration
            response_rules: Response processing rules

        Returns:
            Scraped content (HTML or PDF)
        """
        request_data = {
            "url": url,
            "method": method,
            "data": data,
            "headers": headers,
            "proxyOptions": proxy_options,
            "responseRules": response_rules
        }
        response = self.client.post("/scraper/page", request_data, {"url": url})

        content_type = response.headers.get("content-type", "")
        if "application/pdf" in content_type:
            return {"pdfFile": response.content}
        else:
            json_data = response.json()
            # Decode base64 encoded HTML
            if "encoded_html" in json_data:
                html = base64.b64decode(json_data["encoded_html"]).decode('utf-8')
                return {"html": html}
            return json_data


class ItemsAPI:
    """Items retrieval API"""

    def __init__(self, client: RecallHTTPClient):
        self.client = client

    def get_reader(self, slug: str, language: str = "en") -> Dict:
        """Get reader view of an item"""
        response = self.client.get("/items/reader/", {"slug": slug, "language": language})
        return response.json()

    def get_links(self, slug: str, language: str = "en") -> Dict:
        """Get links associated with an item"""
        response = self.client.get("/items/links/", {"slug": slug, "language": language})
        return response.json()

    def get_reference(self, slug: str, language: str = "en") -> Dict:
        """Get reference view of an item"""
        response = self.client.get("/items/reference/", {"slug": slug, "language": language})
        return response.json()


class ActionsAPI:
    """Content actions API"""

    def __init__(self, client: RecallHTTPClient):
        self.client = client

    def auto_format(self, item_id: str, markdown: str, url: str = "") -> Dict:
        """
        Auto-format markdown content

        Args:
            item_id: Item identifier
            markdown: Markdown to format
            url: Source URL

        Returns:
            Formatted markdown
        """
        query_params = {"itemId": item_id, "url": url}
        data = {"markdown": markdown}
        response = self.client.post("/actions/auto-format", data, query_params)
        return response.json()


class PDFAPI:
    """PDF processing API"""

    def __init__(self, client: RecallHTTPClient):
        self.client = client
        # PDF API uses OCR endpoint
        self.client.base_url = API_URLS["ocr"]

    def extract_markdown_with_ocr(self, pdf_file: bytes) -> Dict:
        """
        Extract text from PDF using OCR

        Args:
            pdf_file: PDF file content as bytes

        Returns:
            Extracted text and title
        """
        response = self.client.post("/pdf", pdf_file, content_type="application/pdf")
        return response.json()


class CacheAPI:
    """Cache management API"""

    def __init__(self, client: RecallHTTPClient):
        self.client = client

    def invalidate_cache(self, field: str, language: str,
                        url: Optional[str] = None,
                        markdown: Optional[str] = None) -> None:
        """
        Invalidate cached content

        Args:
            field: Field to invalidate (e.g., "detailed_summaries")
            language: Language code
            url: Source URL
            markdown: Markdown content
        """
        data = {
            "url": url,
            "field": field,
            "markdown": markdown,
            "language": language
        }
        self.client.post("/cache/invalidate/", data)


class EmailAPI:
    """Email validation API"""

    def __init__(self, client: RecallHTTPClient):
        self.client = client

    def validate(self, email: str) -> Optional[Dict]:
        """Validate an email address"""
        try:
            response = self.client.get(f"/email/validate/", {"email": email})
            return response.json()
        except Exception:
            return None


class UtilsAPI:
    """Utility functions"""

    def __init__(self, client: RecallHTTPClient):
        self.client = client

    def expand_url(self, url: str) -> str:
        """Expand a shortened URL"""
        try:
            response = self.client.get("/expand_url/", {"url": url})
            data = response.json()
            return data.get("url", url)
        except Exception:
            return url


class RecallClient:
    """
    Main Recall.ai API client

    Usage:
        client = RecallClient(auth_token="your_firebase_token")

        # Pull synced data
        cards = client.sync.pull("cards")

        # Generate summary
        summary = client.summary.summarize_markdown(
            url="https://example.com",
            markdown="# Content",
            item_id="item-123"
        )

        # Ask questions
        response = client.chat.ask_question(
            item_id="item-123",
            question="What is this about?",
            url="https://example.com"
        )
    """

    def __init__(self, auth_token: str):
        """
        Initialize Recall client

        Args:
            auth_token: Firebase authentication token (extract from browser)
        """
        if not auth_token:
            raise RecallAuthError("auth_token is required")

        self.http_client = RecallHTTPClient(auth_token)

        # Initialize API endpoints
        self.sync = SyncAPI(self.http_client)
        self.summary = SummaryAPI(self.http_client)
        self.chat = ChatAPI(self.http_client)
        self.questions = QuestionsAPI(self.http_client)
        self.tags = TagsAPI(self.http_client)
        self.entities = EntitiesAPI(self.http_client)
        self.transcript = TranscriptAPI(self.http_client)
        self.scraper = ScraperAPI(self.http_client)
        self.items = ItemsAPI(self.http_client)
        self.actions = ActionsAPI(self.http_client)
        self.cache = CacheAPI(self.http_client)
        self.email = EmailAPI(self.http_client)
        self.utils = UtilsAPI(self.http_client)

        # PDF API uses different base URL
        pdf_client = RecallHTTPClient(auth_token, API_URLS["ocr"])
        self.pdf = PDFAPI(pdf_client)

    @property
    def firebase_config(self) -> Dict:
        """Get Firebase configuration"""
        return FIREBASE_CONFIG


if __name__ == "__main__":
    print(__doc__)
    print("\nFirebase Configuration:")
    print(json.dumps(FIREBASE_CONFIG, indent=2))
    print("\nAPI Base URLs:")
    print(json.dumps(API_URLS, indent=2))
