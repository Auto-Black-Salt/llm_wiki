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
