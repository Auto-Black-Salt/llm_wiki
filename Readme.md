# LLM Wiki

LLM Wiki is a small CLI for maintaining an Obsidian-based knowledge base with an LLM.

Licensed under the MIT License. See [LICENSE](LICENSE).

The workflow is:
- keep raw sources in `raw/` or `archive/`
- convert PDFs and other source files into Markdown
- write original document pages into `obsidian_main/docs/`
- write synthesized wiki pages into `obsidian_main/llm-wiki/`
- query and lint the wiki through the CLI

## Quick Start

```bash
source .venv/bin/activate
llm-wiki init
llm-wiki doctor
llm-wiki ingest archive/Your-File.pdf
```

If you want to rebuild everything from `archive/`:

```bash
scripts/reingest_archive.sh
```

## What it does

- Ingests local files or URLs
- Converts PDFs to Markdown with `opendataloader-pdf`
- Writes docs pages and wiki pages separately
- Tracks ingests in `wiki/log.md`
- Supports query, lint, status, config inspection, and environment checks

## Requirements

- Python 3.11+
- Java 11+ for PDF conversion
- An LM Studio-compatible server on `http://localhost:1234/v1` by default
- `opendataloader-pdf` installed in the active environment

You can verify the environment with:

```bash
llm-wiki doctor
```

## Configuration

The project reads `.wiki-config.toml`.

Current example:

```toml
[llm]
provider = "openai"
model = "gemma-4-31b-jang_4m-crack"
base_url = "http://localhost:1234/v1"
api_key = "lm-studio"

[paths]
raw = "raw"
wiki = "obsidian_main/llm-wiki"
docs = "obsidian_main/docs"
schema = "schema.md"
```

View the active config with:

```bash
llm-wiki config show
```

## CLI

Run `llm-wiki` with no arguments to see the short usage summary.

Available commands:

- `llm-wiki init`
- `llm-wiki ingest`
- `llm-wiki query`
- `llm-wiki lint`
- `llm-wiki status`
- `llm-wiki config show`
- `llm-wiki doctor`

Examples:

```bash
llm-wiki init
llm-wiki ingest archive/Ops-DM\ -\ Version\ 2-v558-20260413_200239.pdf
llm-wiki ingest
llm-wiki query "What are the main themes?"
llm-wiki lint
llm-wiki status
llm-wiki config show
llm-wiki doctor
```

## Ingestion

Ingest a single file:

```bash
llm-wiki ingest archive/Service\ Type\ Codes-v17-20260217_133344.pdf
```

Ingest everything new from `raw/`:

```bash
llm-wiki ingest
```

Reingest everything from `archive/` after clearing the generated Obsidian output:

```bash
scripts/reingest_archive.sh
```

That script removes:
- `obsidian_main/llm-wiki`
- `obsidian_main/docs`

Then it replays every supported source in `archive/` through `llm-wiki ingest`.

## Output Layout

- `obsidian_main/docs/` contains the original document Markdown pages
- `obsidian_main/docs/assets/` contains extracted images
- `obsidian_main/llm-wiki/` contains the synthesized wiki pages
- `obsidian_main/llm-wiki/log.md` records ingests
- `obsidian_main/llm-wiki/index.md` is the wiki entry point

## Doctor

`llm-wiki doctor` checks:
- whether `opendataloader-pdf` is installed
- whether `java` is on PATH
- whether Java is `11+`
- whether the configured LLM endpoint responds

It prints a visible probe line before the LLM request, so it is obvious when the check is running.

## Notes

- The repo uses LM Studio by default, but the model name is configurable in `.wiki-config.toml`.
- The current default model is `gemma-4-31b-jang_4m-crack`.
- If `llm-wiki` prints a usage guide, that means it was called without a subcommand.
