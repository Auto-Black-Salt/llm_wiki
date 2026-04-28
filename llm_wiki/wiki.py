import re
from pathlib import Path

from llm_wiki.llm import strip_image_markdown

WIKI_BLOCK_RE = re.compile(r"```wiki:([^\n]+)\n(.*?)```", re.DOTALL)
LOG_SOURCE_RE = re.compile(r"^## \[.*?\] ingest \| source:(.+)$", re.MULTILINE)
_QUERY_STOP_WORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "do", "does", "for",
    "from", "have", "how", "i", "in", "is", "it", "know", "me", "of", "on",
    "or", "that", "the", "this", "to", "what", "when", "where", "which",
    "who", "why", "with", "would", "you", "your", "about",
}


def parse_wiki_blocks(response: str) -> list[tuple[str, str]]:
    """Extract ```wiki:path ... ``` blocks from LLM response."""
    return [(m.group(1).strip(), m.group(2)) for m in WIKI_BLOCK_RE.finditer(response)]


def write_wiki_blocks(
    project_dir: Path,
    blocks: list[tuple[str, str]],
    wiki_dir: Path | None = None,
) -> list[Path]:
    """Write parsed wiki blocks to disk. Returns list of written paths.

    If wiki_dir is given, any block whose resolved path falls outside wiki_dir
    is remapped into wiki_dir (preserving only the filename), preventing the
    LLM from accidentally writing to the wrong directory.
    """
    resolved_root = project_dir.resolve()
    resolved_wiki = wiki_dir.resolve() if wiki_dir else None
    written = []
    for rel_path, content in blocks:
        full_path = (project_dir / rel_path).resolve()
        if not str(full_path).startswith(str(resolved_root)):
            raise ValueError(f"Refusing to write outside project directory: {rel_path}")
        if full_path.name == "log.md":
            continue  # log is append-only, managed by cli
        # Enforce wiki directory boundary — remap stray paths
        if resolved_wiki and not str(full_path).startswith(str(resolved_wiki) + "/"):
            remapped = resolved_wiki / full_path.name
            full_path = remapped
        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_text(strip_image_markdown(content))
        written.append(full_path)
    return written


def get_ingested_sources(wiki_dir: Path) -> set[str]:
    """Return filenames that appear in log.md as ingested sources."""
    log_path = wiki_dir / "log.md"
    if not log_path.exists():
        return set()
    content = log_path.read_text()
    return {m.group(1).strip() for m in LOG_SOURCE_RE.finditer(content)}


def read_wiki_pages(wiki_dir: Path, page_paths: list[str]) -> str:
    """Read wiki pages by path, skip missing ones, return concatenated content."""
    parts = []
    wiki_prefix = str(wiki_dir.name) + "/"
    for rel_path in page_paths:
        name = rel_path.removeprefix(wiki_prefix).removeprefix("wiki/")
        full_path = wiki_dir / name
        if full_path.exists():
            parts.append(f"--- {rel_path} ---\n{full_path.read_text()}")
    return "\n\n".join(parts)


def read_project_pages(
    project_dir: Path,
    page_paths: list[str],
    wiki_dir: Path,
    docs_dir: Path | None = None,
    question: str | None = None,
    max_chars_per_page: int = 3000,
    max_total_chars: int = 12000,
) -> str:
    """Read wiki and docs pages by path, skip missing ones, return concatenated content.

    If question is provided, excerpts are trimmed around matching terms so the
    query prompt stays small and focused.
    """
    parts = []
    total_chars = 0
    for rel_path in page_paths:
        if rel_path.startswith(f"{wiki_dir.name}/"):
            full_path = wiki_dir / rel_path.removeprefix(f"{wiki_dir.name}/")
        elif docs_dir and rel_path.startswith(f"{docs_dir.name}/"):
            full_path = docs_dir / rel_path.removeprefix(f"{docs_dir.name}/")
        else:
            full_path = project_dir / rel_path
        if full_path.exists():
            page_text = full_path.read_text()
            if question:
                page_text = _excerpt_page_text(page_text, question, max_chars_per_page)
            block = f"--- {rel_path} ---\n{page_text}"
            if question and max_total_chars > 0:
                remaining = max_total_chars - total_chars
                if remaining <= 0:
                    break
                if len(block) > remaining:
                    parts.append(block[:remaining].rstrip() + "\n...[truncated]")
                    break
            parts.append(block)
            total_chars += len(block)
    return "\n\n".join(parts)


def _excerpt_page_text(text: str, question: str, max_chars: int) -> str:
    cleaned = strip_image_markdown(text).strip()
    if len(cleaned) <= max_chars:
        return cleaned
    lower = cleaned.lower()
    candidates = _query_candidates(question)
    best_start = 0
    best_end = min(len(cleaned), max_chars)
    for candidate in candidates:
        idx = lower.find(candidate)
        if idx == -1:
            continue
        start = cleaned.rfind("\n", 0, idx) + 1
        end = min(len(cleaned), idx + len(candidate) + (max_chars * 2 // 3))
        if end - start > max_chars:
            end = min(len(cleaned), start + max_chars)
        best_start = start
        best_end = end
        break
    excerpt = cleaned[best_start:best_end].strip()
    if best_start > 0:
        excerpt = "... " + excerpt
    if best_end < len(cleaned):
        excerpt = excerpt + " ..."
    return excerpt


def _query_candidates(question: str) -> list[str]:
    tokens = [
        token for token in re.findall(r"[A-Za-z0-9]+", question.lower())
        if len(token) > 1 and token not in _QUERY_STOP_WORDS
    ]
    candidates: list[str] = []
    if tokens:
        joined = " ".join(tokens)
        candidates.append(joined)
        candidates.extend(tokens)
        if len(tokens) > 2:
            candidates.extend(" ".join(tokens[i:i + 2]) for i in range(len(tokens) - 1))
    return list(dict.fromkeys(candidates))
