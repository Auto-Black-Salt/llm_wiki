import re
from pathlib import Path

WIKI_BLOCK_RE = re.compile(r"```wiki:([^\n]+)\n(.*?)```", re.DOTALL)
LOG_SOURCE_RE = re.compile(r"^## \[.*?\] ingest \| source:(.+)$", re.MULTILINE)


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
    wiki_prefix = str(wiki_dir.name) + "/"
    for rel_path in page_paths:
        name = rel_path.removeprefix(wiki_prefix).removeprefix("wiki/")
        full_path = wiki_dir / name
        if full_path.exists():
            parts.append(f"--- {rel_path} ---\n{full_path.read_text()}")
    return "\n\n".join(parts)
