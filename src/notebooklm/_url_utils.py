"""URL validation utilities.

These helpers use proper URL parsing to avoid substring matching vulnerabilities
flagged by CodeQL (py/incomplete-url-substring-sanitization).
"""

import re
from urllib.parse import urlparse


def is_youtube_url(url: str) -> bool:
    """Check if a URL is a YouTube video URL.

    Uses proper hostname parsing to avoid substring matching issues
    (e.g., 'evil.com/youtube.com' would incorrectly match with substring check).

    Args:
        url: URL to check

    Returns:
        True if the URL is from YouTube (youtube.com or youtu.be)
    """
    try:
        hostname = (urlparse(url).hostname or "").lower()
        return (
            hostname == "youtube.com" or hostname.endswith(".youtube.com") or hostname == "youtu.be"
        )
    except (AttributeError, TypeError, ValueError):
        return False


def is_google_auth_redirect(url: str) -> bool:
    """Check if a URL is a Google authentication/login page redirect.

    Used to detect when our request to NotebookLM was redirected to
    accounts.google.com due to expired/invalid authentication.

    Args:
        url: URL to check (typically response.url after a request)

    Returns:
        True if the URL is a Google accounts page
    """
    try:
        hostname = (urlparse(url).hostname or "").lower()
        return hostname == "accounts.google.com" or hostname.endswith(".accounts.google.com")
    except (AttributeError, TypeError, ValueError):
        return False


def is_google_drive_url(url: str) -> bool:
    """Check if a URL is a Google Drive or Google Docs/Slides/Sheets URL.

    Args:
        url: URL to check

    Returns:
        True if the URL points to a Google Drive file or Workspace document
    """
    try:
        hostname = (urlparse(url).hostname or "").lower()
        return hostname in {
            "drive.google.com",
            "docs.google.com",
        }
    except (AttributeError, TypeError, ValueError):
        return False


def extract_drive_file_id(url: str) -> str | None:
    """Extract the file/document ID from a Google Drive or Docs URL.

    Handles:
    - drive.google.com/file/d/{ID}/view
    - drive.google.com/open?id={ID}
    - docs.google.com/document/d/{ID}/...
    - docs.google.com/presentation/d/{ID}/...
    - docs.google.com/spreadsheets/d/{ID}/...

    Args:
        url: A Google Drive or Workspace URL

    Returns:
        The file ID string, or None if not extractable
    """
    try:
        from urllib.parse import parse_qs

        parsed = urlparse(url)
        hostname = (parsed.hostname or "").lower()

        if hostname not in {"drive.google.com", "docs.google.com"}:
            return None

        # drive.google.com/open?id=FILE_ID
        if hostname == "drive.google.com" and parsed.path.rstrip("/") in ("/open", "/uc"):
            qs = parse_qs(parsed.query)
            ids = qs.get("id", [])
            return ids[0] if ids else None

        # /file/d/{ID}/... or /document/d/{ID}/... etc.
        segments = parsed.path.lstrip("/").split("/")
        # Find the segment after 'd'
        for i, seg in enumerate(segments):
            if seg == "d" and i + 1 < len(segments):
                file_id = segments[i + 1]
                return file_id if file_id else None

        return None
    except (AttributeError, TypeError, ValueError):
        return None


def detect_drive_mime_type(url: str) -> str:
    """Detect the likely MIME type of a Google Drive file from its URL.

    Args:
        url: A Google Drive or Workspace URL

    Returns:
        A MIME type string. Defaults to 'application/pdf' for generic Drive files.
    """
    try:
        parsed = urlparse(url)
        path = parsed.path.lower()
        segments = path.lstrip("/").split("/")
        doc_type = segments[0] if segments else ""

        if doc_type == "document":
            return "application/vnd.google-apps.document"
        if doc_type == "presentation":
            return "application/vnd.google-apps.presentation"
        if doc_type == "spreadsheets":
            return "application/vnd.google-apps.spreadsheet"
        # drive.google.com/file/d/... — could be anything; default to pdf
        return "application/pdf"
    except (AttributeError, TypeError, ValueError):
        return "application/pdf"


def contains_google_auth_redirect(text: str) -> bool:
    """Check if text (HTML/JSON) contains a Google auth redirect URL.

    Extracts URLs from text and checks if any point to accounts.google.com.
    Used to detect login page redirects in HTML response bodies.

    Args:
        text: HTML or JSON text that may contain URLs

    Returns:
        True if any URL in the text points to Google accounts
    """
    # Find URLs in the text (href="...", src="...", or standalone https://...)
    url_pattern = r'https?://[^\s"\'<>]+'
    urls = re.findall(url_pattern, text)
    return any(is_google_auth_redirect(url) for url in urls)
