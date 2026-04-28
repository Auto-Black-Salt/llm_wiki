import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import httpx
from readability import Document
from lxml import html as lxml_html

MAX_CHARS = 50_000  # ~12k tokens, safe for most context windows


@dataclass
class ParsedSource:
    filename: str
    text: str
    raw_bytes: Optional[bytes] = None
    images: list[tuple[str, bytes]] = field(default_factory=list)  # (filename, data)
    source_path: Optional[str] = None


def parse_source(path_or_url: str) -> ParsedSource:
    """Parse a file path or URL into a ParsedSource."""
    if path_or_url.startswith(("http://", "https://")):
        if _is_youtube_url(path_or_url):
            return _fetch_youtube(path_or_url)
        return _fetch_url(path_or_url)
    path = Path(path_or_url)
    if path.suffix.lower() in (".pdf", ".docx", ".doc"):
        return _parse_docling(path)
    return ParsedSource(filename=path.name, text=path.read_text(), source_path=str(path))


def chunk_text(text: str, max_chars: int = MAX_CHARS) -> list[str]:
    """Split text into chunks of at most max_chars, breaking at paragraph boundaries."""
    if len(text) <= max_chars:
        return [text]
    chunks = []
    while text:
        if len(text) <= max_chars:
            chunks.append(text)
            break
        split_at = text.rfind("\n\n", 0, max_chars)
        if split_at == -1:
            split_at = text.rfind("\n", 0, max_chars)
        if split_at == -1:
            split_at = max_chars
        chunks.append(text[:split_at])
        text = text[split_at:].lstrip("\n")
    return chunks


def _is_youtube_url(url: str) -> bool:
    return "youtube.com/watch" in url or "youtu.be/" in url


def _extract_video_id(url: str) -> str:
    if "youtu.be/" in url:
        return url.split("youtu.be/")[1].split("?")[0].split("/")[0]
    from urllib.parse import urlparse, parse_qs
    return parse_qs(urlparse(url).query)["v"][0]


def _fetch_youtube(url: str) -> ParsedSource:
    from youtube_transcript_api import YouTubeTranscriptApi  # lazy import

    video_id = _extract_video_id(url)

    # Fetch video title from page metadata
    try:
        resp = httpx.get(url, follow_redirects=True, timeout=15)
        title_match = re.search(r'<meta property="og:title" content="([^"]+)"', resp.text)
        title = title_match.group(1) if title_match else video_id
    except Exception:
        title = video_id

    # Fetch transcript — try all available languages if English not found
    api = YouTubeTranscriptApi()
    try:
        transcript = api.fetch(video_id)
    except Exception:
        try:
            transcript_list = api.list(video_id)
            transcript = transcript_list.find_transcript(
                [t.language_code for t in transcript_list]
            ).fetch()
        except Exception as e:
            raise ValueError(f"No transcript available for {url}: {e}") from e

    text = "\n".join(snippet.text for snippet in transcript)
    slug = re.sub(r"[^\w\s-]", "", title).strip().replace(" ", "-")[:60]
    filename = f"{slug}-{video_id}.md"
    full_text = f"# {title}\n\n**YouTube:** {url}\n\n## Transcript\n\n{text}"
    return ParsedSource(filename=filename, text=full_text)


def _fetch_url(url: str) -> ParsedSource:
    response = httpx.get(url, follow_redirects=True, timeout=30)
    response.raise_for_status()
    doc = Document(response.text)
    summary_html = doc.summary()
    tree = lxml_html.fromstring(summary_html)
    text = tree.text_content()
    if not text.strip():
        raise ValueError(f"Could not extract readable content from {url}")
    slug = re.sub(r"[^\w-]", "-", url.split("//")[-1].split("/")[0])[:40]
    hash_suffix = hashlib.md5(url.encode()).hexdigest()[:4]
    filename = f"{slug}-{hash_suffix}.html"
    return ParsedSource(filename=filename, text=text, raw_bytes=response.content)


def _parse_docling(path: Path) -> ParsedSource:
    try:
        from docling.document_converter import DocumentConverter
    except ModuleNotFoundError as e:
        raise ValueError(
            "Document conversion requires the 'docling' package. "
            "Install it in the active environment."
        ) from e

    try:
        converter = DocumentConverter()
        result = converter.convert(str(path))
        text = result.document.export_to_markdown()
    except Exception as e:
        raise ValueError(f"Could not convert {path} with Docling: {e}") from e

    if not text.strip():
        raise ValueError(f"Docling produced empty Markdown for {path}")

    return ParsedSource(filename=path.name, text=text, source_path=str(path))
