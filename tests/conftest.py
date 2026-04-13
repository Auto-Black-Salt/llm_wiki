import pytest
from pathlib import Path


@pytest.fixture
def project_dir(tmp_path):
    """A temp directory scaffolded as a wiki project."""
    (tmp_path / "raw").mkdir()
    (tmp_path / "raw" / "assets").mkdir()
    (tmp_path / "wiki").mkdir()
    (tmp_path / "wiki" / "index.md").write_text("# Wiki Index\n")
    (tmp_path / "wiki" / "log.md").write_text("")
    (tmp_path / "schema.md").write_text("# Schema\nMaintain wiki pages.\n")
    (tmp_path / ".wiki-config.toml").write_text(
        '[llm]\nprovider = "openai"\nmodel = "local-model"\n'
        'base_url = "http://localhost:1234/v1"\napi_key = "lm-studio"\n\n'
        '[paths]\nraw = "raw"\nwiki = "wiki"\nschema = "schema.md"\n'
    )
    return tmp_path
