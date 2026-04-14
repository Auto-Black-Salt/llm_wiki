import hashlib
from datetime import date
from pathlib import Path
from typing import Optional
import typer
import httpx
from llm_wiki.config import load_config, find_project_dir
from llm_wiki.llm import (
    build_ingest_messages,
    build_query_step1_messages,
    build_query_step2_messages,
    build_lint_messages,
    parse_relevant_pages,
    call_llm,
)
from llm_wiki.sources import parse_source, chunk_text
from llm_wiki.wiki import parse_wiki_blocks, write_wiki_blocks, get_ingested_sources, read_wiki_pages

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
docs = "docs"
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
    (project_dir / "archive").mkdir(exist_ok=True)
    (project_dir / "wiki").mkdir(exist_ok=True)
    (project_dir / "docs").mkdir(exist_ok=True)

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
    typer.echo("  docs/        <- original documents as Markdown (with images)")
    typer.echo("  wiki/        <- LLM-summarized pages (don't edit manually)")
    typer.echo("  schema.md    <- LLM instructions (customize as you go)")


@app.command()
def ingest(path_or_url: Optional[str] = typer.Argument(None)):
    """Ingest a source file or URL. With no argument, scans raw/ for new files."""
    project_dir = find_project_dir(Path.cwd())
    config = load_config(project_dir)
    wiki_dir = project_dir / config.paths.wiki
    raw_dir = project_dir / config.paths.raw

    if path_or_url is None:
        ingested = get_ingested_sources(wiki_dir)
        new_files = [
            f for f in raw_dir.rglob("*")
            if f.is_file()
            and "assets" not in f.parts
            and f.name not in ingested
            and not f.name.startswith(".")
        ]
        if not new_files:
            typer.echo("No new files to ingest.")
            return
        for f in sorted(new_files):
            _ingest_one(str(f), config, project_dir)
    else:
        if path_or_url.startswith(("http://", "https://")):
            try:
                source = parse_source(path_or_url)
            except httpx.ConnectError:
                typer.echo(f"Error: could not fetch {path_or_url}", err=True)
                raise typer.Exit(1)
            except ValueError as e:
                typer.echo(f"Error: {e}", err=True)
                raise typer.Exit(1)
            if source.raw_bytes:
                raw_path = raw_dir / source.filename
                if raw_path.exists():
                    h = hashlib.md5(path_or_url.encode()).hexdigest()[:4]
                    raw_path = raw_dir / f"{raw_path.stem}-{h}{raw_path.suffix}"
                raw_path.write_bytes(source.raw_bytes)
            _ingest_one_parsed(source.filename, source.text, config, project_dir)
        else:
            _ingest_one(path_or_url, config, project_dir)


def _write_docs_page(source, config, project_dir: Path) -> Optional[str]:
    """Write the full document as Markdown to the docs directory. Returns the relative path."""
    if not config.paths.docs:
        return None
    docs_dir = project_dir / config.paths.docs
    assets_dir = docs_dir / "assets"
    if source.images:
        assets_dir.mkdir(parents=True, exist_ok=True)
        for img_filename, img_data in source.images:
            (assets_dir / img_filename).write_bytes(img_data)
    docs_dir.mkdir(parents=True, exist_ok=True)
    stem = Path(source.filename).stem
    page_path = docs_dir / f"{stem}.md"
    page_path.write_text(f"# {stem}\n\n*Source: `{source.filename}`*\n\n{source.text}\n")
    return str(page_path.relative_to(project_dir))



def _ingest_one(path: str, config, project_dir: Path) -> None:
    """Parse a local file, write docs page, ingest to llm-wiki, then archive."""
    try:
        source = parse_source(path)
    except Exception as e:
        typer.echo(f"Error reading {path}: {e}", err=True)
        return

    docs_link = _write_docs_page(source, config, project_dir)
    if docs_link:
        typer.echo(f"Docs page written: {docs_link}")

    _ingest_one_parsed(source.filename, source.text, config, project_dir, docs_link=docs_link)

    raw_dir = (project_dir / config.paths.raw).resolve()
    file_path = Path(path).resolve()
    if str(file_path).startswith(str(raw_dir)):
        archive_dir = project_dir / "archive"
        archive_dir.mkdir(exist_ok=True)
        dest = archive_dir / file_path.name
        file_path.rename(dest)
        typer.echo(f"Archived {file_path.name} → archive/")


def _read_existing_pages(wiki_dir: Path) -> str:
    """Read all existing wiki pages (excluding index and log) into a single string."""
    pages = sorted(
        p for p in wiki_dir.glob("**/*.md")
        if p.name not in ("index.md", "log.md")
    )
    if not pages:
        return ""
    return "\n\n".join(
        f"--- {p.relative_to(wiki_dir.parent)} ---\n{p.read_text()}"
        for p in pages
    )


def _ingest_one_parsed(filename: str, text: str, config, project_dir: Path) -> list[Path]:
    """Run the LLM ingest loop for already-parsed source text. Returns written page paths."""
    wiki_dir = project_dir / config.paths.wiki
    schema_path = project_dir / config.paths.schema
    schema = schema_path.read_text() if schema_path.exists() else ""
    index_path = wiki_dir / "index.md"
    index = index_path.read_text() if index_path.exists() else ""
    all_written: list[Path] = []

    chunks = chunk_text(text)
    for i, chunk in enumerate(chunks):
        chunk_label = f"{filename} (part {i+1}/{len(chunks)})" if len(chunks) > 1 else filename
        typer.echo(f"Ingesting {chunk_label}...")

        existing_pages = _read_existing_pages(wiki_dir) if i > 0 else ""
        messages = build_ingest_messages(
            schema, index, chunk_label, chunk,
            wiki_path=config.paths.wiki,
            existing_pages=existing_pages,
        )
        try:
            response = call_llm(config, messages)
        except Exception as e:
            if "connection" in str(e).lower() or "connect" in str(e).lower():
                typer.echo(
                    f"Cannot connect to {config.llm.base_url} — is it running?", err=True
                )
                raise typer.Exit(1)
            raise

        blocks = parse_wiki_blocks(response)
        if not blocks:
            typer.echo(f"Warning: LLM returned no wiki blocks for {chunk_label}.")
            typer.echo(response)
            continue

        written = write_wiki_blocks(project_dir, blocks)
        all_written.extend(written)
        if index_path.exists():
            index = index_path.read_text()

    typer.echo(f"Done: {filename}")
    return all_written


@app.command()
def status():
    """Show wiki stats: page count, source count, last log entry."""
    project_dir = find_project_dir(Path.cwd())
    config = load_config(project_dir)
    wiki_dir = project_dir / config.paths.wiki
    raw_dir = project_dir / config.paths.raw

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


@app.command()
def query(
    question: str = typer.Argument(..., help="Question to ask the wiki"),
    save: bool = typer.Option(False, "--save", help="Save the answer as a wiki page"),
):
    """Ask a question and get an answer synthesized from the wiki."""
    project_dir = find_project_dir(Path.cwd())
    config = load_config(project_dir)
    wiki_dir = project_dir / config.paths.wiki
    schema_path = project_dir / config.paths.schema
    schema = schema_path.read_text() if schema_path.exists() else ""
    index_path = wiki_dir / "index.md"
    index = index_path.read_text() if index_path.exists() else ""

    # Step 1: identify relevant pages
    step1_messages = build_query_step1_messages(schema, index, question)
    try:
        step1_response = call_llm(config, step1_messages)
    except Exception as e:
        if "connection" in str(e).lower() or "connect" in str(e).lower():
            typer.echo(f"Cannot connect to {config.llm.base_url} — is it running?", err=True)
            raise typer.Exit(1)
        raise

    relevant = parse_relevant_pages(step1_response)
    if not relevant:
        typer.echo("(LLM found no directly relevant pages — answering from index only)")
        pages_text = index
    else:
        pages_text = read_wiki_pages(wiki_dir, relevant)

    # Step 2: synthesize answer
    step2_messages = build_query_step2_messages(schema, pages_text, question)
    try:
        answer = call_llm(config, step2_messages)
    except Exception as e:
        if "connection" in str(e).lower() or "connect" in str(e).lower():
            typer.echo(f"Cannot connect to {config.llm.base_url} — is it running?", err=True)
            raise typer.Exit(1)
        raise

    typer.echo(answer)

    if save:
        slug = date.today().isoformat()
        short = "".join(c if c.isalnum() else "-" for c in question[:40]).strip("-")
        filename = f"query-{slug}-{short}.md"
        save_path = wiki_dir / filename
        save_path.write_text(f"# Query: {question}\n\n{answer}\n")
        typer.echo(f"\nSaved to wiki/{filename}")


@app.command()
def lint():
    """Health-check the wiki for contradictions, orphans, stale claims, and gaps."""
    project_dir = find_project_dir(Path.cwd())
    config = load_config(project_dir)
    wiki_dir = project_dir / config.paths.wiki
    schema_path = project_dir / config.paths.schema
    schema = schema_path.read_text() if schema_path.exists() else ""

    all_pages = list(wiki_dir.glob("**/*.md")) if wiki_dir.exists() else []
    if not all_pages:
        typer.echo("Wiki is empty — nothing to lint.")
        return

    pages_content = "\n\n".join(
        f"--- {p.relative_to(project_dir)} ---\n{p.read_text()}"
        for p in sorted(all_pages)
    )

    messages = build_lint_messages(schema, pages_content)
    try:
        report = call_llm(config, messages)
    except Exception as e:
        if "connection" in str(e).lower() or "connect" in str(e).lower():
            typer.echo(f"Cannot connect to {config.llm.base_url} — is it running?", err=True)
            raise typer.Exit(1)
        raise

    typer.echo(report)
