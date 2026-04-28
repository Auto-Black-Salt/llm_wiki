import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass
class LLMConfig:
    provider: str
    model: str
    base_url: str
    api_key: str


@dataclass
class PathsConfig:
    raw: str
    wiki: str
    schema: str
    docs: Optional[str] = None
    docling_artifacts_path: Optional[str] = None


@dataclass
class Config:
    llm: LLMConfig
    paths: PathsConfig


def find_project_dir(start: Path) -> Path:
    """Walk up from start until .wiki-config.toml is found."""
    for directory in [start, *start.parents]:
        if (directory / ".wiki-config.toml").exists():
            return directory
    raise FileNotFoundError(
        f"No .wiki-config.toml found in {start} or any parent. Run 'llm-wiki init' first."
    )


def load_config(project_dir: Path) -> Config:
    config_path = project_dir / ".wiki-config.toml"
    if not config_path.exists():
        raise FileNotFoundError(
            f"No .wiki-config.toml found in {project_dir}. Run 'llm-wiki init' first."
        )
    with open(config_path, "rb") as f:
        data = tomllib.load(f)
    try:
        return Config(
            llm=LLMConfig(**data["llm"]),
            paths=PathsConfig(**data["paths"]),
        )
    except (KeyError, TypeError) as e:
        raise ValueError(
            f"Invalid .wiki-config.toml: {e}. Check [llm] and [paths] sections."
        ) from e
