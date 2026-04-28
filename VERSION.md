# Version History

This file tracks the tool versions for the `llm-wiki` project.

## 0.7.0

- Added a project-local Docling artifacts path for PDF conversion
- Wired Docling to use local artifacts instead of implicit Hub downloads at runtime
- Documented the local Docling setup in the README and doctor command

## 0.6.0

- Kept source document images in `obsidian_main/docs/assets/<document>/`
- Rewrote absolute Docling image paths to relative Obsidian links
- Stripped image markdown from the knowledge-graph wiki pages
- Preserved docs pages as a human-readable source layer alongside the wiki summary layer

## 0.5.0

- Switched document conversion to Docling for PDFs and office documents
- Added `llm-wiki config show`
- Added `llm-wiki doctor` with model discovery and config write-back
- Added the `scripts/reingest_archive.sh` workflow
- Added the MIT license

## 0.1.0

- Initial CLI scaffolding
- Basic ingest, query, lint, and status commands
- Raw source handling and wiki output directories
