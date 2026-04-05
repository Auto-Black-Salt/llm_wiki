from pathlib import Path
from typing import Optional
import typer

app = typer.Typer(help="LLM Wiki — maintain a personal knowledge wiki with an LLM.")

_DEFAULT_CONFIG = """\
[llm]
provider = "openai"
model = "local-model"
base_url = "http://localhost:1234/v1"
api_key = "lm-studio"

[paths]
raw = "raw"
wiki = "wiki"
schema = "schema.md"
"""

_STARTER_SCHEMA = """\
# Wiki Schema

## Page Conventions

- All wiki pages use Markdown format
- Each page starts with a `# Title` heading
- Link to related pages using `[[Page Name]]` or `[Page Name](page-name.md)` syntax
- Add YAML frontmatter with `tags:` and `sources:` fields when relevant

## index.md Format

```markdown
# Wiki Index

## Concepts
- [[concept-name]] — one-line description

## Entities
- [[entity-name]] — one-line description

## Sources
- [[source-title]] — one-line summary
```

## log.md Format

Append-only log. Each entry:

```markdown
## [YYYY-MM-DD] ingest | source:<filename>
- Created: page1.md, page2.md
- Updated: existing-page.md
```

## Maintenance Rules

1. When ingesting a source: create a summary page, update all relevant entity/concept pages
2. Note contradictions with existing pages explicitly on both pages
3. Maintain cross-references — if you mention an entity, link to its page
4. Keep index.md current — add new pages, update one-line descriptions
"""


@app.command()
def init():
    """Scaffold a new wiki project in the current directory."""
    project_dir = Path.cwd()
    (project_dir / "raw" / "assets").mkdir(parents=True, exist_ok=True)
    (project_dir / "wiki").mkdir(exist_ok=True)

    index_path = project_dir / "wiki" / "index.md"
    if not index_path.exists():
        index_path.write_text("# Wiki Index\n")

    log_path = project_dir / "wiki" / "log.md"
    if not log_path.exists():
        log_path.write_text("")

    schema_path = project_dir / "schema.md"
    if not schema_path.exists():
        schema_path.write_text(_STARTER_SCHEMA)

    config_path = project_dir / ".wiki-config.toml"
    if not config_path.exists():
        config_path.write_text(_DEFAULT_CONFIG)
        typer.echo("Created .wiki-config.toml — edit model name to match your LM Studio model.")
    else:
        typer.echo(".wiki-config.toml already exists, skipping.")

    typer.echo("Wiki initialized. Directory structure:")
    typer.echo("  raw/         <- drop your source files here")
    typer.echo("  wiki/        <- LLM-generated pages (don't edit manually)")
    typer.echo("  schema.md    <- LLM instructions (customize as you go)")


@app.command()
def status():
    """Show wiki stats: page count, source count, last log entry."""
    from llm_wiki.config import load_config
    config = load_config(Path.cwd())
    wiki_dir = Path(config.paths.wiki)
    raw_dir = Path(config.paths.raw)

    wiki_pages = [
        f for f in wiki_dir.glob("**/*.md")
        if f.name not in ("index.md", "log.md")
    ] if wiki_dir.exists() else []

    raw_files = [
        f for f in raw_dir.iterdir()
        if f.is_file() and not f.name.startswith(".")
    ] if raw_dir.exists() else []

    log_path = wiki_dir / "log.md"
    last_entry = "(none)"
    if log_path.exists():
        entries = [l for l in log_path.read_text().splitlines() if l.startswith("## [")]
        if entries:
            last_entry = entries[-1]

    typer.echo(f"Wiki pages:    {len(wiki_pages)}")
    typer.echo(f"Raw sources:   {len(raw_files)}")
    typer.echo(f"Last activity: {last_entry}")
