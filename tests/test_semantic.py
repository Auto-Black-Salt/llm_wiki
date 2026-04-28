from llm_wiki.semantic import semantic_relevant_pages


def test_semantic_relevant_pages_prefers_matching_content(tmp_path):
    wiki_dir = tmp_path / "wiki"
    wiki_dir.mkdir()
    (wiki_dir / "index.md").write_text("# Index\n")
    (wiki_dir / "log.md").write_text("")
    (wiki_dir / "alpha.md").write_text("# Alpha\nBananas apples oranges.")
    (wiki_dir / "beta.md").write_text("# Beta\nSpace rockets and moons.")

    relevant = semantic_relevant_pages(wiki_dir, "apples and bananas")

    assert relevant[0] == "wiki/alpha.md"
    assert "wiki/beta.md" not in relevant
