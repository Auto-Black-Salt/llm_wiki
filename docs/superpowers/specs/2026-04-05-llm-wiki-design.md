# LLM Wiki — Design Spec
Date: 2026-04-05

## Overview

A Python CLI tool that maintains a personal knowledge wiki using LLMs. You supply source documents (files or URLs); the LLM reads them, extracts key information, and incrementally builds and maintains a structured collection of interlinked markdown files. The wiki is a persistent, compounding artifact — cross-references are pre-built, contradictions flagged, synthesis already done.

## Directory Structure

```
my-wiki/                        ← project directory (run llm-wiki from here)
├── .wiki-config.toml           ← per-project config (provider, model, paths)
├── raw/                        ← immutable source documents (user adds these)
│   └── assets/                 ← downloaded images from web clips
├── wiki/                       ← LLM-generated markdown (LLM writes, user reads)
│   ├── index.md                ← catalog of all wiki pages (auto-updated on ingest)
│   └── log.md                  ← append-only history of ingests/queries/lints
└── schema.md                   ← instructions for the LLM on wiki conventions
```

## Configuration

Per-project `.wiki-config.toml`:

```toml
[llm]
provider = "openai"           # LM Studio is OpenAI-compatible (default)
model = "local-model"         # model loaded in LM Studio
base_url = "http://localhost:1234/v1"
api_key = "lm-studio"

[paths]
raw = "raw"
wiki = "wiki"
schema = "schema.md"
```

Other providers (Anthropic, OpenAI cloud) are available by changing `provider`, `model`, `base_url`, and `api_key`. LiteLLM handles all provider abstraction.

## CLI Commands

```
llm-wiki init                      # scaffold structure + starter schema.md + default config
llm-wiki ingest                    # scan raw/ for new files (not in log.md), ingest all
llm-wiki ingest <path-or-url>      # ingest a specific file (txt/md/pdf) or web URL
llm-wiki query "<question>"        # ask a question, answer synthesized from wiki
llm-wiki query "<question>" --save # same, but also files the answer as a wiki page
llm-wiki lint                      # health-check wiki for contradictions/orphans/gaps
llm-wiki status                    # show page count, source count, last log entry
```

Built with [Typer](https://typer.tiangolo.com/) for automatic `--help` generation.

### Ingest — "new files" detection

`llm-wiki ingest` (no args) diffs `raw/` against `log.md`. A file is "new" if it has no corresponding log entry. The log is the canonical record of what has been processed.

### Source parsing

| Type | Library |
|------|---------|
| `.txt`, `.md` | stdlib `open()` |
| `.pdf` | `opendataloader-pdf` |
| Web URL | `httpx` + `readability-lxml` (extracts main article content) |

Web URLs: raw HTML saved to `raw/<slug>-<hash>.html`, extracted text sent to LLM.

## LLM Interaction Model

`schema.md` is always included in the system prompt so the LLM knows wiki conventions. All file writes use a fenced-block output format that Python parses — the LLM never touches the filesystem directly.

### Fenced-block output format

The LLM outputs file changes as:

````
```wiki:wiki/some-page.md
# Page Title
...content...
```
````

Python extracts these blocks and writes them to disk.

### Ingest prompt

```
system: <schema.md>
         You are a wiki maintainer. When given a source document:
         1. Write or update wiki pages as needed
         2. Output each file as: ```wiki:path/to/page.md ... ```
         3. Update index.md and log.md in the same format

user:   Current index.md: <contents>
         New source (<filename>): <parsed text>
         Process this source and output all file changes.
```

### Query prompt

```
system: <schema.md>
user:   Current index.md: <contents>
         Relevant wiki pages: <contents>
         Question: <user question>
         Answer with citations to wiki pages.
```

### Lint prompt

```
system: <schema.md>
user:   All wiki pages: <contents>
         Identify: contradictions, orphan pages, stale claims,
         missing cross-references, data gaps.
```

## Data Flow

```
ingest <url>
  → httpx fetch → readability extract → save to raw/
  → LLM prompt (schema + index + source text)
  → parse ```wiki: blocks from response
  → write wiki pages to disk
  → append log.md entry (only after all writes succeed)
  → update index.md

query "<question>"
  → LLM prompt (schema + index.md)
  → LLM identifies relevant pages → read them
  → LLM synthesizes answer with citations
  → print to stdout (optionally write to wiki/)

lint
  → read all wiki pages
  → LLM prompt (schema + all pages)
  → print health report (optionally file to wiki/)
```

## Error Handling

| Scenario | Behavior |
|----------|----------|
| LM Studio not running | Catch connection error, print: "Cannot connect to LM Studio at http://localhost:1234/v1 — is it running?" |
| LLM returns no `wiki:` blocks | Print warning + raw LLM response (nothing silently lost) |
| Source exceeds context window | Chunk source, ingest in passes with continuation notes in prompt |
| Web fetch fails / empty extract | Abort with clear error, do not send to LLM |
| Partial ingest crash | Log entry only written after all files saved; re-run reprocesses cleanly |
| `raw/` filename collision | Append short hash suffix (e.g. `article-a3f2.html`) rather than overwrite |

## Dependencies

```
typer          # CLI framework
litellm        # multi-provider LLM abstraction
opendataloader-pdf  # PDF parsing
httpx          # async HTTP client for web fetch
readability-lxml  # article extraction from HTML
tomllib        # config parsing (stdlib in Python 3.11+)
```

## Search / Query Strategy

Phase 1 (this spec): index.md-based retrieval. LLM reads index, identifies relevant page names, Python reads those files, LLM synthesizes answer.

Phase 2 (future): optional `--semantic` flag using a local vector store (e.g. ChromaDB) for embedding-based retrieval. Not in scope for initial implementation.
