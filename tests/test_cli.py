import os
import pytest
from typer.testing import CliRunner
from llm_wiki.cli import app

runner = CliRunner()


def test_init_creates_structure(tmp_path):
    old_cwd = os.getcwd()
    os.chdir(tmp_path)
    try:
        result = runner.invoke(app, ["init"], catch_exceptions=False)
        assert result.exit_code == 0
        assert (tmp_path / "raw").is_dir()
        assert (tmp_path / "raw" / "assets").is_dir()
        assert (tmp_path / "wiki").is_dir()
        assert (tmp_path / "wiki" / "index.md").exists()
        assert (tmp_path / "wiki" / "log.md").exists()
        assert (tmp_path / "schema.md").exists()
        assert (tmp_path / ".wiki-config.toml").exists()
        config_text = (tmp_path / ".wiki-config.toml").read_text()
        assert "http://localhost:1234/v1" in config_text
    finally:
        os.chdir(old_cwd)


def test_init_does_not_overwrite_existing_config(tmp_path):
    old_cwd = os.getcwd()
    os.chdir(tmp_path)
    try:
        runner.invoke(app, ["init"])
        (tmp_path / ".wiki-config.toml").write_text("custom = true\n")
        runner.invoke(app, ["init"])
        assert "custom = true" in (tmp_path / ".wiki-config.toml").read_text()
    finally:
        os.chdir(old_cwd)


def test_status(project_dir):
    old_cwd = os.getcwd()
    os.chdir(project_dir)
    try:
        (project_dir / "wiki" / "page1.md").write_text("# P1\n")
        (project_dir / "wiki" / "page2.md").write_text("# P2\n")
        (project_dir / "raw" / "source.txt").write_text("content")
        (project_dir / "wiki" / "log.md").write_text(
            "## [2026-04-05] ingest | source:source.txt\n"
        )
        result = runner.invoke(app, ["status"], catch_exceptions=False)
        assert result.exit_code == 0
        assert "2" in result.output  # 2 wiki pages
        assert "1" in result.output  # 1 raw source
        assert "2026-04-05" in result.output
    finally:
        os.chdir(old_cwd)


def test_ingest_file(project_dir, monkeypatch):
    old_cwd = os.getcwd()
    os.chdir(project_dir)
    try:
        source = project_dir / "raw" / "article.md"
        source.write_text("# Article\nSome content about Topic A.")

        llm_response = (
            "```wiki:wiki/topic-a.md\n# Topic A\nSummary of Topic A.\n```\n"
            "```wiki:wiki/index.md\n# Wiki Index\n\n## Concepts\n- [[topic-a]] — Topic A summary\n```\n"
            "```wiki:wiki/log.md\n## [2026-04-05] ingest | source:article.md\n- Created: topic-a.md\n```\n"
        )
        monkeypatch.setattr("llm_wiki.cli.call_llm", lambda cfg, msgs: llm_response)

        result = runner.invoke(app, ["ingest", str(source)], catch_exceptions=False)
        assert result.exit_code == 0
        assert (project_dir / "wiki" / "topic-a.md").exists()
        assert "Topic A" in (project_dir / "wiki" / "topic-a.md").read_text()
    finally:
        os.chdir(old_cwd)


def test_ingest_no_args_picks_up_new_files(project_dir, monkeypatch):
    old_cwd = os.getcwd()
    os.chdir(project_dir)
    try:
        source = project_dir / "raw" / "notes.txt"
        source.write_text("Some notes.")

        llm_response = (
            "```wiki:wiki/notes.md\n# Notes\nSummary.\n```\n"
            "```wiki:wiki/index.md\n# Wiki Index\n```\n"
            "```wiki:wiki/log.md\n## [2026-04-05] ingest | source:notes.txt\n```\n"
        )
        monkeypatch.setattr("llm_wiki.cli.call_llm", lambda cfg, msgs: llm_response)

        result = runner.invoke(app, ["ingest"], catch_exceptions=False)
        assert result.exit_code == 0
        assert (project_dir / "wiki" / "notes.md").exists()
    finally:
        os.chdir(old_cwd)


def test_ingest_no_args_skips_already_ingested(project_dir, monkeypatch):
    old_cwd = os.getcwd()
    os.chdir(project_dir)
    try:
        source = project_dir / "raw" / "old.txt"
        source.write_text("Old content.")
        (project_dir / "wiki" / "log.md").write_text(
            "## [2026-04-04] ingest | source:old.txt\n"
        )
        called = []
        monkeypatch.setattr("llm_wiki.cli.call_llm", lambda cfg, msgs: called.append(1) or "")
        result = runner.invoke(app, ["ingest"], catch_exceptions=False)
        assert result.exit_code == 0
        assert len(called) == 0
        assert "No new files" in result.output
    finally:
        os.chdir(old_cwd)


def test_ingest_no_wiki_blocks_warns(project_dir, monkeypatch):
    old_cwd = os.getcwd()
    os.chdir(project_dir)
    try:
        source = project_dir / "raw" / "file.txt"
        source.write_text("Content.")
        monkeypatch.setattr("llm_wiki.cli.call_llm", lambda cfg, msgs: "Just prose, no blocks.")
        result = runner.invoke(app, ["ingest", str(source)], catch_exceptions=False)
        assert result.exit_code == 0
        assert "Warning" in result.output or "warning" in result.output
    finally:
        os.chdir(old_cwd)


def test_query_prints_answer(project_dir, monkeypatch):
    old_cwd = os.getcwd()
    os.chdir(project_dir)
    try:
        (project_dir / "wiki" / "topic-a.md").write_text("# Topic A\nDetailed info about A.")
        (project_dir / "wiki" / "index.md").write_text(
            "# Wiki Index\n\n## Concepts\n- [[topic-a]] — info about A\n"
        )

        step1_response = "```relevant_pages\nwiki/topic-a.md\n```"
        step2_response = "Topic A is described in [[topic-a]]."
        responses = iter([step1_response, step2_response])
        monkeypatch.setattr("llm_wiki.cli.call_llm", lambda cfg, msgs: next(responses))

        result = runner.invoke(app, ["query", "What is Topic A?"], catch_exceptions=False)
        assert result.exit_code == 0
        assert "Topic A" in result.output
    finally:
        os.chdir(old_cwd)


def test_query_save_flag(project_dir, monkeypatch):
    old_cwd = os.getcwd()
    os.chdir(project_dir)
    try:
        (project_dir / "wiki" / "index.md").write_text("# Wiki Index\n")

        step1_response = "```relevant_pages\nwiki/index.md\n```"
        step2_response = "The answer is 42."
        responses = iter([step1_response, step2_response])
        monkeypatch.setattr("llm_wiki.cli.call_llm", lambda cfg, msgs: next(responses))

        result = runner.invoke(
            app, ["query", "What is the answer?", "--save"], catch_exceptions=False
        )
        assert result.exit_code == 0
        saved = list((project_dir / "wiki").glob("query-*.md"))
        assert len(saved) == 1
        assert "42" in saved[0].read_text()
    finally:
        os.chdir(old_cwd)


def test_query_no_relevant_pages(project_dir, monkeypatch):
    old_cwd = os.getcwd()
    os.chdir(project_dir)
    try:
        monkeypatch.setattr(
            "llm_wiki.cli.call_llm", lambda cfg, msgs: "No relevant_pages block here."
        )
        result = runner.invoke(app, ["query", "What?"], catch_exceptions=False)
        assert result.exit_code == 0
        assert "no relevant pages" in result.output.lower() or "directly" in result.output.lower()
    finally:
        os.chdir(old_cwd)
