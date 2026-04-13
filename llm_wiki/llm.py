import re
import litellm
from llm_wiki.config import Config

RELEVANT_PAGES_RE = re.compile(r"```relevant_pages\n(.*?)```", re.DOTALL)

_INGEST_INSTRUCTIONS = """
You are a wiki maintainer. When given a source document:
1. Write or update wiki pages as needed (summaries, entity pages, concept pages).
2. Output EVERY file change as a fenced block:
   ```wiki:wiki/page-name.md
   # Page Title
   ...content...
   ```
3. Always output updated wiki/index.md and wiki/log.md in the same format.
4. Log format for new entry: ## [YYYY-MM-DD] ingest | source:<filename>
   followed by bullet list of created/updated pages.
""".strip()

_QUERY_STEP1_INSTRUCTIONS = """
Given an index of wiki pages and a user question, identify which pages are relevant.
Output ONLY this fenced block — no other text:
```relevant_pages
wiki/page1.md
wiki/page2.md
```
""".strip()

_LINT_INSTRUCTIONS = """
Health-check the wiki. Identify:
- Contradictions between pages
- Orphan pages with no inbound links
- Stale claims superseded by newer content
- Missing cross-references
- Important concepts without their own page
- Data gaps that could be filled with a web search

Output a clear Markdown report.
""".strip()


def build_ingest_messages(
    schema: str, index: str, filename: str, source_text: str
) -> list[dict]:
    return [
        {"role": "system", "content": f"{schema}\n\n{_INGEST_INSTRUCTIONS}"},
        {
            "role": "user",
            "content": (
                f"Current wiki/index.md:\n{index}\n\n"
                f"New source ({filename}):\n{source_text}\n\n"
                "Process this source and output all file changes."
            ),
        },
    ]


def build_query_step1_messages(schema: str, index: str, question: str) -> list[dict]:
    return [
        {"role": "system", "content": f"{schema}\n\n{_QUERY_STEP1_INSTRUCTIONS}"},
        {
            "role": "user",
            "content": f"Index:\n{index}\n\nQuestion: {question}\n\nWhich pages are relevant?",
        },
    ]


def build_query_step2_messages(schema: str, pages: str, question: str) -> list[dict]:
    return [
        {"role": "system", "content": schema},
        {
            "role": "user",
            "content": (
                f"Relevant wiki pages:\n{pages}\n\n"
                f"Question: {question}\n\n"
                "Answer thoroughly with citations to the wiki pages above."
            ),
        },
    ]


def build_lint_messages(schema: str, pages: str) -> list[dict]:
    return [
        {"role": "system", "content": f"{schema}\n\n{_LINT_INSTRUCTIONS}"},
        {
            "role": "user",
            "content": (
                f"Health-check the wiki for contradictions, orphans, stale claims, "
                f"missing links, and data gaps:\n\nAll wiki pages:\n{pages}"
            ),
        },
    ]


def parse_relevant_pages(response: str) -> list[str]:
    """Extract page paths from a ```relevant_pages ... ``` block."""
    match = RELEVANT_PAGES_RE.search(response)
    if not match:
        return []
    return [line.strip() for line in match.group(1).splitlines() if line.strip()]


def call_llm(config: Config, messages: list[dict]) -> str:
    """Call LiteLLM with the given messages. Returns response text."""
    kwargs: dict = {
        "model": config.llm.model,
        "messages": messages,
    }
    if config.llm.base_url:
        kwargs["api_base"] = config.llm.base_url
    if config.llm.api_key:
        kwargs["api_key"] = config.llm.api_key
    response = litellm.completion(**kwargs)
    return response.choices[0].message.content
