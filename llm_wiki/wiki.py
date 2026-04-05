import re
from pathlib import Path

WIKI_BLOCK_RE = re.compile(r"```wiki:([^\n]+)\n(.*?)```", re.DOTALL)
LOG_SOURCE_RE = re.compile(r"^## \[.*?\] ingest \| source:(.+)$", re.MULTILINE)


def parse_wiki_blocks(response: str) -> list[tuple[str, str]]:
    """Extract ```wiki:path ... ``` blocks from LLM response."""
    return [(m.group(1).strip(), m.group(2)) for m in WIKI_BLOCK_RE.finditer(response)]


def write_wiki_blocks(project_dir: Path, blocks: list[tuple[str, str]]) -> list[Path]:
    """Write parsed wiki blocks to disk. Returns list of written paths."""
    written = []
    for rel_path, content in blocks:
        full_path = project_dir / rel_path
        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_text(content)
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
    for rel_path in page_paths:
        # strip leading "wiki/" prefix if present to get path within wiki_dir
        name = rel_path.removeprefix("wiki/")
        full_path = wiki_dir / name
        if full_path.exists():
            parts.append(f"--- {rel_path} ---\n{full_path.read_text()}")
    return "\n\n".join(parts)
