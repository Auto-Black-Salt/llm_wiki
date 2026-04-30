# Version History

This file tracks the tool versions for the `llm-wiki` project.

## 0.9.3

- Extracted embedded pictures from PDF ingestion so docs pages match the DOCX behaviour
- Preserved code-block line breaks in PDF docs pages via Docling code enrichment
- URL-encoded image paths so docs with spaces (or other special characters) render correctly in Obsidian and standard Markdown viewers

## 0.9.2

- Reduced query prompt size by extracting focused excerpts from large docs pages
- Improved query latency for topics buried deep inside the original documents
- Kept the docs/wiki split intact while making answer synthesis cheaper

## 0.9.1

- Made ingest summaries denser so source facts, routes, and examples are preserved better
- Improved retrieval signal for large docs directories by keeping more useful detail in the generated pages

## 0.9.0

- Added docs-page retrieval to query so important phrases can come from source markdown
- Merged local semantic fallback with the graph query path
- Improved query results for topics that only appear in original documents

## 0.8.0

- Added `llm-wiki query --semantic` with a local TF-IDF retrieval path
- Kept semantic retrieval fully offline and free of Hugging Face dependencies
- Documented the new query mode in the README

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
