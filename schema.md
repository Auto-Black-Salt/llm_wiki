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
