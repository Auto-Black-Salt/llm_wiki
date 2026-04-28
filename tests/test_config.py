import pytest
from pathlib import Path
from llm_wiki.config import load_config, Config, LLMConfig, PathsConfig


def test_load_config(project_dir):
    config = load_config(project_dir)
    assert isinstance(config, Config)
    assert config.llm.model == "local-model"
    assert config.llm.base_url == "http://localhost:1234/v1"
    assert config.llm.api_key == "lm-studio"
    assert config.paths.raw == "raw"
    assert config.paths.wiki == "wiki"
    assert config.paths.schema == "schema.md"
    assert config.paths.docling_artifacts_path == ".docling-models"


def test_load_config_missing(tmp_path):
    with pytest.raises(FileNotFoundError, match="llm-wiki init"):
        load_config(tmp_path)


def test_config_dataclasses():
    llm = LLMConfig(provider="anthropic", model="claude-3", base_url="", api_key="key")
    paths = PathsConfig(raw="raw", wiki="wiki", schema="schema.md")
    config = Config(llm=llm, paths=paths)
    assert config.llm.provider == "anthropic"
    assert config.paths.wiki == "wiki"


def test_load_config_bad_key(tmp_path):
    (tmp_path / ".wiki-config.toml").write_text(
        '[llm]\nprovider = "openai"\nmodle = "typo"\n'  # typo: modle instead of model
        'base_url = ""\napi_key = ""\n\n'
        '[paths]\nraw = "raw"\nwiki = "wiki"\nschema = "schema.md"\n'
    )
    with pytest.raises(ValueError, match="Invalid .wiki-config.toml"):
        load_config(tmp_path)
