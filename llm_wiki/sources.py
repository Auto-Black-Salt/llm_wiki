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


def parse_source(path_or_url: str) -> ParsedSource:
    """Parse a file path or URL into a ParsedSource."""
    if path_or_url.startswith(("http://", "https://")):
        if _is_youtube_url(path_or_url):
            return _fetch_youtube(path_or_url)
        return _fetch_url(path_or_url)
    path = Path(path_or_url)
    if path.suffix.lower() == ".pdf":
        return _parse_pdf(path)
    if path.suffix.lower() in (".docx", ".doc"):
        return _parse_docx(path)
    return ParsedSource(filename=path.name, text=path.read_text())


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
    from youtube_transcript_api import YouTubeTranscriptApi, NoTranscriptFound, TranscriptsDisabled  # lazy import

    video_id = _extract_video_id(url)

    # Fetch video title from page metadata
    try:
        resp = httpx.get(url, follow_redirects=True, timeout=15)
        title_match = re.search(r'<meta property="og:title" content="([^"]+)"', resp.text)
        title = title_match.group(1) if title_match else video_id
    except Exception:
        title = video_id

    # Fetch transcript (prefer manual, fall back to auto-generated)
    try:
        transcript = YouTubeTranscriptApi.get_transcript(video_id)
    except (NoTranscriptFound, TranscriptsDisabled) as e:
        raise ValueError(f"No transcript available for {url}: {e}") from e

    text = "\n".join(entry["text"] for entry in transcript)
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


def _parse_docx(path: Path) -> ParsedSource:
    import docx  # lazy import — only needed for Word docs
    doc = docx.Document(str(path))
    parts = []
    images = []
    img_counter = 0

    for para in doc.paragraphs:
        if para.text.strip():
            parts.append(para.text)

    # Extract images from the document's inline shapes / relationships
    for rel in doc.part.rels.values():
        if "image" in rel.reltype:
            img_data = rel.target_part.blob
            ext = rel.target_part.content_type.split("/")[-1]
            if ext == "jpeg":
                ext = "jpg"
            img_counter += 1
            img_filename = f"{path.stem}-img{img_counter}.{ext}"
            images.append((img_filename, img_data))
            parts.append(f"![[assets/{img_filename}]]")

    return ParsedSource(filename=path.name, text="\n".join(parts), images=images)


_DOT_LEADER_RE = re.compile(r'\.{4,}')
_ORPHAN_BULLET_RE = re.compile(r'^([•·▪▸]|\d+\.)$')


def _is_toc_page(page) -> bool:
    """Return True if the page is mostly TOC dot-leader lines."""
    lines = [l.strip() for l in page.get_text().splitlines() if l.strip()]
    if not lines:
        return False
    toc_lines = sum(1 for l in lines if _DOT_LEADER_RE.search(l))
    return toc_lines / len(lines) > 0.3


def _bbox_overlaps(a: tuple, b: tuple) -> bool:
    """Return True if two (x0, y0, x1, y1) bboxes overlap."""
    return not (a[2] < b[0] or b[2] < a[0] or a[3] < b[1] or b[3] < a[1])


def _fix_lists(text: str) -> str:
    """Join orphaned bullet/number paragraphs with the following paragraph."""
    paras = text.split("\n\n")
    result = []
    i = 0
    while i < len(paras):
        stripped = paras[i].strip()
        if _ORPHAN_BULLET_RE.match(stripped):
            # Find next non-empty paragraph
            j = i + 1
            while j < len(paras) and not paras[j].strip():
                j += 1
            if j < len(paras):
                prefix = "- " if stripped in ('•', '·', '▪', '▸') else stripped + " "
                result.append(prefix + paras[j].strip())
                i = j + 1
                continue
        result.append(paras[i])
        i += 1
    return "\n\n".join(result)


def _page_to_text(page) -> str:
    """Extract page text with tables as Markdown and lists reconstructed."""
    try:
        tabs = page.find_tables()
        table_regions = [
            (t.bbox, re.sub(r'<br\s*/?>', ' ', t.to_markdown()))
            for t in tabs.tables
        ]
    except Exception:
        table_regions = []

    table_bboxes = [bbox for bbox, _ in table_regions]

    # Collect non-table text blocks with x and y for sorting and grouping
    pieces: list[tuple[float, float, str]] = []  # (y0, x0, text)
    for block in page.get_text("blocks"):
        x0, y0, x1, y1, text, _, block_type = block
        if block_type != 0:
            continue
        text = text.strip()
        if not text:
            continue
        if any(_bbox_overlaps((x0, y0, x1, y1), tb) for tb in table_bboxes):
            continue
        pieces.append((y0, x0, text))

    # Add tables at their vertical position
    for bbox, md in table_regions:
        pieces.append((bbox[1], bbox[0], md))

    # Sort by y then x so bullet comes before its text on the same line
    pieces.sort(key=lambda p: (p[0], p[1]))

    # Merge blocks that share the same vertical position (within 5pt) onto one line.
    # Never merge multiline content (tables) — they must stay as their own paragraph.
    lines: list[tuple[float, str]] = []
    for y, _x, text in pieces:
        is_table = "\n" in text
        prev_is_table = lines and "\n" in lines[-1][1]
        if lines and not is_table and not prev_is_table and abs(y - lines[-1][0]) < 5:
            lines[-1] = (lines[-1][0], lines[-1][1] + " " + text)
        else:
            lines.append((y, text))

    raw = "\n\n".join(text for _, text in lines)
    return _fix_lists(raw)


def _build_markdown_toc(toc: list) -> str:
    """Convert pymupdf TOC [(level, title, page), ...] to clean Markdown."""
    if not toc:
        return ""
    lines = ["## Table of Contents\n"]
    for level, title, page in toc:
        indent = "  " * (level - 1)
        lines.append(f"{indent}- {title} *(p.{page})*")
    return "\n".join(lines)


def _parse_pdf(path: Path) -> ParsedSource:
    import pymupdf  # lazy import — only needed for PDFs
    doc = pymupdf.open(str(path))
    pages_text = []
    images = []
    seen_xrefs: set[int] = set()
    for page in doc:
        if _is_toc_page(page):
            continue  # replaced by clean Markdown TOC below
        pages_text.append(_page_to_text(page))
        for img_info in page.get_images(full=True):
            xref = img_info[0]
            if xref in seen_xrefs:
                continue
            seen_xrefs.add(xref)
            img_data = doc.extract_image(xref)
            ext = img_data["ext"]
            img_filename = f"{path.stem}-img{len(images) + 1}.{ext}"
            images.append((img_filename, img_data["image"]))
            pages_text.append(f"![[assets/{img_filename}]]")

    clean_text = "\n\n".join(pages_text)

    toc_md = _build_markdown_toc(doc.get_toc())
    if toc_md:
        clean_text = toc_md + "\n\n---\n\n" + clean_text

    return ParsedSource(filename=path.name, text=clean_text, images=images)
