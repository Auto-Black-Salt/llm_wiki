import hashlib
import re
from dataclasses import dataclass
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


def parse_source(path_or_url: str) -> ParsedSource:
    """Parse a file path or URL into a ParsedSource."""
    if path_or_url.startswith(("http://", "https://")):
        return _fetch_url(path_or_url)
    path = Path(path_or_url)
    if path.suffix.lower() == ".pdf":
        return _parse_pdf(path)
    return ParsedSource(filename=path.name, text=path.read_text())


def chunk_text(text: str, max_chars: int = MAX_CHARS) -> list[str]:
    """Split text into chunks of at most max_chars characters."""
    if len(text) <= max_chars:
        return [text]
    return [text[i : i + max_chars] for i in range(0, len(text), max_chars)]


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


def _parse_pdf(path: Path) -> ParsedSource:
    import pymupdf  # lazy import — only needed for PDFs
    doc = pymupdf.open(str(path))
    text = "\n".join(page.get_text() for page in doc)
    return ParsedSource(filename=path.name, text=text)
