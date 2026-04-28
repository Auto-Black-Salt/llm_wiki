from llm_wiki.semantic import semantic_relevant_pages


def test_semantic_relevant_pages_prefers_matching_content(tmp_path):
    project_dir = tmp_path
    wiki_dir = tmp_path / "wiki"
    wiki_dir.mkdir()
    (wiki_dir / "index.md").write_text("# Index\n")
    (wiki_dir / "log.md").write_text("")
    (wiki_dir / "alpha.md").write_text("# Alpha\nBananas apples oranges.")
    (wiki_dir / "beta.md").write_text("# Beta\nSpace rockets and moons.")
    docs_dir = tmp_path / "obsidian_main" / "docs"
    docs_dir.mkdir(parents=True, exist_ok=True)
    (docs_dir / "Ops-DM.md").write_text(
        "# Ops-DM\n\nTriangle route example OS 213 VIE - LEJ OS 213 LEJ - NUE OS 213 NUE - VIE\n"
    )

    relevant = semantic_relevant_pages(project_dir, "apples and bananas", wiki_dir, docs_dir)

    assert relevant[0] == "wiki/alpha.md"
    assert "wiki/beta.md" not in relevant

    docs_relevant = semantic_relevant_pages(project_dir, "Triangle route", wiki_dir, docs_dir)
    assert "obsidian_main/docs/Ops-DM.md" in docs_relevant
