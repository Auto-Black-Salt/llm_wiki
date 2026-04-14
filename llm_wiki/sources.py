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


def _page_to_text(page) -> str:
    """Extract page text with tables rendered as Markdown tables."""
    try:
        tabs = page.find_tables()
        table_regions = [(t.bbox, t.to_markdown()) for t in tabs.tables]
    except Exception:
        table_regions = []

    table_bboxes = [bbox for bbox, _ in table_regions]

    # Collect non-table text blocks
    pieces: list[tuple[float, str]] = []
    for block in page.get_text("blocks"):
        x0, y0, x1, y1, text, _, block_type = block
        if block_type != 0:
            continue
        text = text.strip()
        if not text:
            continue
        if any(_bbox_overlaps((x0, y0, x1, y1), tb) for tb in table_bboxes):
            continue
        pieces.append((y0, text))

    # Add tables at their vertical position
    for bbox, md in table_regions:
        pieces.append((bbox[1], md))

    pieces.sort(key=lambda p: p[0])
    return "\n\n".join(text for _, text in pieces)


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
