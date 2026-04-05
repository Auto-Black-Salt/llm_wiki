import tomllib
from dataclasses import dataclass
from pathlib import Path


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


@dataclass
class Config:
    llm: LLMConfig
    paths: PathsConfig


def load_config(project_dir: Path) -> Config:
    config_path = project_dir / ".wiki-config.toml"
    if not config_path.exists():
        raise FileNotFoundError(
            f"No .wiki-config.toml found in {project_dir}. Run 'llm-wiki init' first."
        )
    with open(config_path, "rb") as f:
        data = tomllib.load(f)
    return Config(
        llm=LLMConfig(**data["llm"]),
        paths=PathsConfig(**data["paths"]),
    )
