import pytest
from pathlib import Path
from llm_wiki.wiki import (
    parse_wiki_blocks,
    write_wiki_blocks,
    get_ingested_sources,
    read_wiki_pages,
    read_project_pages,
)


def test_parse_wiki_blocks_single():
    response = "```wiki:wiki/page.md\n# Title\ncontent\n```"
    blocks = parse_wiki_blocks(response)
    assert blocks == [("wiki/page.md", "# Title\ncontent\n")]


def test_parse_wiki_blocks_multiple():
    response = (
        "Some preamble.\n"
        "```wiki:wiki/a.md\nA content\n```\n"
        "Middle text.\n"
        "```wiki:wiki/b.md\nB content\n```"
    )
    blocks = parse_wiki_blocks(response)
    assert len(blocks) == 2
    assert blocks[0] == ("wiki/a.md", "A content\n")
    assert blocks[1] == ("wiki/b.md", "B content\n")


def test_parse_wiki_blocks_empty():
    assert parse_wiki_blocks("No blocks here.") == []


def test_write_wiki_blocks(tmp_path):
    blocks = [
        ("wiki/page.md", "# Title\ncontent\n"),
        ("wiki/subdir/other.md", "# Other\n"),
    ]
    write_wiki_blocks(tmp_path, blocks)
    assert (tmp_path / "wiki" / "page.md").read_text() == "# Title\ncontent\n"
    assert (tmp_path / "wiki" / "subdir" / "other.md").read_text() == "# Other\n"


def test_write_wiki_blocks_strips_images(tmp_path):
    blocks = [
        ("wiki/page.md", "# Title\n\n![Figure](assets/doc/figure.png)\ncontent\n"),
    ]
    write_wiki_blocks(tmp_path, blocks)
    assert "![Figure]" not in (tmp_path / "wiki" / "page.md").read_text()
    assert "content" in (tmp_path / "wiki" / "page.md").read_text()


def test_get_ingested_sources_empty(tmp_path):
    wiki_dir = tmp_path / "wiki"
    wiki_dir.mkdir()
    assert get_ingested_sources(wiki_dir) == set()


def test_get_ingested_sources_no_log(tmp_path):
    wiki_dir = tmp_path / "wiki"
    wiki_dir.mkdir()
    assert get_ingested_sources(wiki_dir) == set()


def test_get_ingested_sources_with_log(tmp_path):
    wiki_dir = tmp_path / "wiki"
    wiki_dir.mkdir()
    (wiki_dir / "log.md").write_text(
        "## [2026-04-05] ingest | source:article.pdf\n"
        "## [2026-04-05] ingest | source:notes.md\n"
    )
    result = get_ingested_sources(wiki_dir)
    assert result == {"article.pdf", "notes.md"}


def test_read_wiki_pages(tmp_path):
    wiki_dir = tmp_path / "wiki"
    wiki_dir.mkdir()
    (wiki_dir / "page1.md").write_text("# Page 1\n")
    (wiki_dir / "page2.md").write_text("# Page 2\n")
    result = read_wiki_pages(wiki_dir, ["wiki/page1.md", "wiki/page2.md"])
    assert "# Page 1" in result
    assert "# Page 2" in result


def test_read_wiki_pages_missing_skipped(tmp_path):
    wiki_dir = tmp_path / "wiki"
    wiki_dir.mkdir()
    (wiki_dir / "exists.md").write_text("# Exists\n")
    result = read_wiki_pages(wiki_dir, ["wiki/exists.md", "wiki/missing.md"])
    assert "# Exists" in result


def test_read_project_pages_uses_focused_excerpt(tmp_path):
    project_dir = tmp_path
    wiki_dir = project_dir / "wiki"
    docs_dir = project_dir / "obsidian_main" / "docs"
    docs_dir.mkdir(parents=True)
    wiki_dir.mkdir()
    page = docs_dir / "ops.md"
    page.write_text(
        "# Intro\n" + ("filler text\n" * 200) + "## Triangle route example OS\n"
        "3 Legs OS 213 VIE - LEJ OS 213 LEJ - NUE OS 213 NUE - VIE\n" + ("tail\n" * 200)
    )
    result = read_project_pages(
        project_dir,
        ["docs/ops.md"],
        wiki_dir,
        docs_dir,
        question="What do you know about Triangle route?",
    )
    assert "Triangle route example OS" in result
    assert "3 Legs OS 213 VIE - LEJ" in result
    assert len(result) < len(page.read_text())


def test_write_wiki_blocks_path_traversal(tmp_path):
    blocks = [("../../etc/passwd", "evil")]
    with pytest.raises(ValueError, match="Refusing to write outside"):
        write_wiki_blocks(tmp_path, blocks)
