import hashlib
import importlib.util
import re as _re
from datetime import date
from pathlib import Path
from typing import Optional
import click
import typer
import httpx
import tomllib
from llm_wiki.config import load_config, find_project_dir
from llm_wiki.llm import (
    build_ingest_messages,
    build_query_step1_messages,
    build_query_step2_messages,
    build_lint_messages,
    parse_relevant_pages,
    strip_image_markdown,
    call_llm,
)
from llm_wiki.sources import parse_source, chunk_text
from llm_wiki.wiki import parse_wiki_blocks, write_wiki_blocks, get_ingested_sources, read_wiki_pages

app = typer.Typer(help="LLM Wiki — maintain a personal knowledge wiki with an LLM.")
config_app = typer.Typer(help="Inspect the active project configuration.")


app.add_typer(config_app, name="config")


@app.command()
def version():
    """Print the installed package version and version history file."""
    typer.echo(f"llm-wiki {_read_project_version()}")
    typer.echo("Version history: VERSION.md")


@app.callback(invoke_without_command=True)
def main(ctx: typer.Context):
    """Show a short command guide when the CLI is invoked without a subcommand."""
    if ctx.invoked_subcommand is not None:
        return

    typer.echo("Usage: llm-wiki <command> [options]")
    typer.echo("")
    typer.echo("Available commands:")
    typer.echo("  init    Scaffold a new wiki project in the current directory")
    typer.echo("  config  Inspect the active project configuration")
    typer.echo("  version Print the installed package version")
    typer.echo("  ingest  Ingest a source file, URL, or all new files in raw/")
    typer.echo("  query   Ask a question against the wiki")
    typer.echo("  lint    Check the wiki for contradictions, orphans, and gaps")
    typer.echo("  status  Show page counts and the last activity")
    typer.echo("  doctor  Check the local runtime, Docling, and LLM endpoint")
    typer.echo("")
    typer.echo("Examples:")
    typer.echo("  llm-wiki init")
    typer.echo("  llm-wiki config show")
    typer.echo("  llm-wiki version")
    typer.echo("  llm-wiki doctor")
    typer.echo("  llm-wiki ingest archive/example.pdf")
    typer.echo("  llm-wiki query 'What changed?'\n")
    raise typer.Exit(1)

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


@config_app.command("show")
def config_show():
    """Print the active project config."""
    project_dir = find_project_dir(Path.cwd())
    config = load_config(project_dir)
    config_path = project_dir / ".wiki-config.toml"

    typer.echo(f"Project: {project_dir}")
    typer.echo(f"Config:   {config_path}")
    typer.echo("")
    typer.echo("[llm]")
    typer.echo(f'provider = "{config.llm.provider}"')
    typer.echo(f'model = "{config.llm.model}"')
    typer.echo(f'base_url = "{config.llm.base_url}"')
    typer.echo(f'api_key = "{config.llm.api_key}"')
    typer.echo("")
    typer.echo("[paths]")
    typer.echo(f'raw = "{config.paths.raw}"')
    typer.echo(f'wiki = "{config.paths.wiki}"')
    typer.echo(f'schema = "{config.paths.schema}"')
    typer.echo(f'docs = "{config.paths.docs}"')


@app.command()
def doctor():
    """Check the project config and local runtime prerequisites."""
    project_dir = find_project_dir(Path.cwd())
    config = load_config(project_dir)

    typer.echo(f"Project: {project_dir}")
    typer.echo(f"Model:   {config.llm.model}")
    typer.echo(f"Base URL: {config.llm.base_url}")
    typer.echo("")

    problems: list[str] = []

    docling_available = importlib.util.find_spec("docling") is not None
    if docling_available:
        typer.echo("docling: OK")
    else:
        typer.echo("docling: missing")
        problems.append("Install docling in the active environment.")

    models = _fetch_available_models(config.llm.base_url)
    if models:
        typer.echo("available models:")
        for idx, model_name in enumerate(models, start=1):
            selected = " (current)" if model_name == config.llm.model else ""
            typer.echo(f"  {idx}. {model_name}{selected}")

        if typer.confirm("Change the configured model?", default=False):
            choice = typer.prompt(
                "Choose a model number",
                type=click.IntRange(1, len(models)),
            )
            chosen_model = models[choice - 1]
            _update_config_model(project_dir, chosen_model)
            config.llm.model = chosen_model
            typer.echo(f'Updated config: model = "{chosen_model}"')
    else:
        typer.echo("available models: none found")
        problems.append("No models were returned by the configured LLM endpoint.")

    try:
        print(f"llm: probing configured model ({config.llm.model})...", flush=True)
        response = call_llm(
            config,
            [
                {
                    "role": "user",
                    "content": "Reply with exactly: pong",
                }
            ],
        )
        if "pong" in response.lower():
            typer.echo("llm: OK")
        else:
            typer.echo(f"llm: unexpected response ({response!r})")
            problems.append("The configured LLM responded, but not with the expected probe output.")
    except Exception as e:
        typer.echo(f"llm: error ({e})")
        problems.append(f"Could not reach the configured LLM: {e}")

    typer.echo("")
    if problems:
        typer.echo("Problems:")
        for problem in problems:
            typer.echo(f"- {problem}")
        raise typer.Exit(1)

    typer.echo("Everything looks good.")
    raise typer.Exit(0)


def _fetch_available_models(base_url: str) -> list[str]:
    """Fetch model IDs from an OpenAI-compatible /models endpoint."""
    if not base_url:
        return []
    url = f"{base_url.rstrip('/')}/models"
    try:
        response = httpx.get(url, timeout=10)
        response.raise_for_status()
        payload = response.json()
    except Exception as e:
        typer.echo(f"available models: unable to query {url} ({e})")
        return []

    data = payload.get("data", []) if isinstance(payload, dict) else []
    models: list[str] = []
    for item in data:
        if isinstance(item, dict) and item.get("id"):
            models.append(item["id"])
    return list(dict.fromkeys(models))


def _read_project_version() -> str:
    """Read the project version from pyproject.toml."""
    project_root = Path(__file__).resolve().parent.parent
    pyproject_path = project_root / "pyproject.toml"
    with pyproject_path.open("rb") as f:
        data = tomllib.load(f)
    return str(data["project"]["version"])


def _update_config_model(project_dir: Path, model: str) -> None:
    """Update the [llm].model entry in .wiki-config.toml in place."""
    config_path = project_dir / ".wiki-config.toml"
    text = config_path.read_text()
    updated, count = _re.subn(
        r'(^\s*model\s*=\s*")[^"]*(")',
        rf'\1{model}\2',
        text,
        count=1,
        flags=_re.MULTILINE,
    )
    if count != 1:
        raise ValueError("Could not find [llm].model in .wiki-config.toml")
    config_path.write_text(updated)


@app.command()
def ingest(
    path_or_url: Optional[str] = typer.Argument(None),
    update: bool = typer.Option(False, "--update", help="Re-ingest and update existing wiki pages."),
):
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
            ingested = get_ingested_sources(wiki_dir)
            if source.filename in ingested and not update:
                typer.echo(f"Already ingested: {source.filename}. Use --update to re-ingest.")
                return
            if source.raw_bytes:
                raw_path = raw_dir / source.filename
                if raw_path.exists():
                    h = hashlib.md5(path_or_url.encode()).hexdigest()[:4]
                    raw_path = raw_dir / f"{raw_path.stem}-{h}{raw_path.suffix}"
                raw_path.write_bytes(source.raw_bytes)
            docs_link = _write_docs_page(source, config, project_dir)
            if docs_link:
                typer.echo(f"Docs page written: {docs_link}")
            _ingest_one_parsed(source.filename, source.text, config, project_dir, docs_link=docs_link, is_update=update)
            archive_dir = project_dir / "archive"
            archive_dir.mkdir(exist_ok=True)
            (archive_dir / source.filename).write_text(source.text)
            typer.echo(f"Archived {source.filename} → archive/")
        else:
            ingested = get_ingested_sources(wiki_dir)
            filename = Path(path_or_url).name
            if filename in ingested and not update:
                typer.echo(f"Already ingested: {filename}. Use --update to re-ingest.")
                return
            _ingest_one(path_or_url, config, project_dir, is_update=update)


def _write_docs_page(source, config, project_dir: Path) -> Optional[str]:
    """Write the full document as Markdown to the docs directory. Returns the relative path."""
    if not config.paths.docs:
        return None
    docs_dir = project_dir / config.paths.docs
    docs_dir.mkdir(parents=True, exist_ok=True)
    stem = Path(source.filename).stem
    page_path = docs_dir / f"{stem}.md"
    assets_dir = docs_dir / "assets" / stem

    source_path = getattr(source, "source_path", None)
    if source_path and Path(source_path).suffix.lower() in {".pdf", ".docx", ".doc"}:
        try:
            _write_docling_docs_page(source_path, page_path, assets_dir)
            page_markdown = page_path.read_text()
            page_path.write_text(f"> *Source: `{source.filename}`*\n\n{page_markdown}\n")
        except Exception as e:
            typer.echo(
                f"Warning: could not preserve images in {source.filename}: {e}",
                err=True,
            )
            page_path.write_text(
                f"> *Source: `{source.filename}`*\n\n{source.text}\n"
            )
    elif Path(source.filename).suffix.lower() == ".md":
        # Already Markdown — write as-is with a source note prepended
        page_path.write_text(f"> *Source: `{source.filename}`*\n\n{source.text}\n")
    else:
        page_path.write_text(f"# {stem}\n\n*Source: `{source.filename}`*\n\n{source.text}\n")

    # Return path relative to vault root (common parent of wiki and docs), without .md
    # e.g. obsidian_main/docs/MyDoc.md → docs/MyDoc  (valid Obsidian [[link]])
    vault_root = Path(config.paths.wiki).parts[0]  # e.g. "obsidian_main"
    obsidian_link = str(page_path.relative_to(project_dir / vault_root).with_suffix(""))
    return obsidian_link


def _write_docling_docs_page(source_path: str, page_path: Path, assets_dir: Path) -> None:
    """Convert a local source document to Markdown with referenced images."""
    try:
        from docling.document_converter import DocumentConverter
        from docling_core.types.doc import ImageRefMode
    except ModuleNotFoundError as e:
        raise ValueError(
            "Document conversion requires the 'docling' package. "
            "Install it in the active environment."
        ) from e

    converter = DocumentConverter()
    result = converter.convert(source_path)
    assets_dir.mkdir(parents=True, exist_ok=True)
    result.document.save_as_markdown(
        page_path,
        artifacts_dir=assets_dir,
        image_mode=ImageRefMode.REFERENCED,
    )
    _rewrite_docs_asset_links(page_path, assets_dir)


def _rewrite_docs_asset_links(page_path: Path, assets_dir: Path) -> None:
    """Normalize Docling image links to be relative to the docs page."""
    page_text = page_path.read_text()
    asset_root = assets_dir.resolve().as_posix()
    relative_root = assets_dir.relative_to(page_path.parent).as_posix()
    page_text = page_text.replace(asset_root, relative_root)
    if asset_root != str(assets_dir):
        page_text = page_text.replace(str(assets_dir.resolve()), relative_root)
    page_path.write_text(page_text)



def _ingest_one(path: str, config, project_dir: Path, is_update: bool = False) -> None:
    """Parse a local file, write docs page, ingest to llm-wiki, then archive."""
    try:
        source = parse_source(path)
    except Exception as e:
        typer.echo(f"Error reading {path}: {e}", err=True)
        return

    docs_link = _write_docs_page(source, config, project_dir)
    if docs_link:
        typer.echo(f"Docs page written: {docs_link}")

    _ingest_one_parsed(source.filename, source.text, config, project_dir, docs_link=docs_link, is_update=is_update)

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


def _ingest_one_parsed(
    filename: str, text: str, config, project_dir: Path,
    docs_link: Optional[str] = None,
    is_update: bool = False,
) -> list[Path]:
    """Run the LLM ingest loop for already-parsed source text. Returns written page paths."""
    wiki_dir = project_dir / config.paths.wiki
    schema_path = project_dir / config.paths.schema
    schema = schema_path.read_text() if schema_path.exists() else ""
    index_path = wiki_dir / "index.md"
    index = index_path.read_text() if index_path.exists() else ""
    all_written: list[Path] = []

    text = strip_image_markdown(text)
    chunks = chunk_text(text)
    for i, chunk in enumerate(chunks):
        chunk_label = f"{filename} (part {i+1}/{len(chunks)})" if len(chunks) > 1 else filename
        typer.echo(f"{'Updating' if is_update else 'Ingesting'} {chunk_label}...")

        existing_pages = _read_existing_pages(wiki_dir) if (i > 0 or is_update) else ""
        messages = build_ingest_messages(
            schema, index, chunk_label, chunk,
            wiki_path=config.paths.wiki,
            existing_pages=existing_pages,
            docs_link=docs_link,
            is_update=is_update,
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

        written = write_wiki_blocks(project_dir, blocks, wiki_dir=wiki_dir)
        all_written.extend(written)
        if index_path.exists():
            index = index_path.read_text()

    # Append log entry (never overwrite — log is append-only)
    non_meta = [
        p for p in all_written
        if p.name not in ("index.md", "log.md")
    ]
    if non_meta:
        log_path = wiki_dir / "log.md"
        entry_lines = [f"## [{date.today().isoformat()}] ingest | source:{filename}"]
        for p in non_meta:
            rel = p.relative_to(project_dir)
            entry_lines.append(f"- {rel}")
        entry_lines.append("")
        with log_path.open("a") as f:
            f.write("\n".join(entry_lines) + "\n")

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


_DOCS_LINK_RE = _re.compile(r'\[\[([^\]]*docs[^\]]*)\]\]')


def _extract_docs_links(pages_text: str) -> list[str]:
    """Extract all [[...docs...]] links found in wiki page content."""
    return list(dict.fromkeys(_DOCS_LINK_RE.findall(pages_text)))


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

    docs_links = _extract_docs_links(pages_text)
    if docs_links:
        typer.echo("\n**Original documents:**")
        for link in docs_links:
            typer.echo(f"  [[{link}]]")

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
