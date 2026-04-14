import re
from typing import Optional
import litellm
from llm_wiki.config import Config

RELEVANT_PAGES_RE = re.compile(r"```relevant_pages\n(.*?)```", re.DOTALL)

_INGEST_INSTRUCTIONS_TEMPLATE = """
You are a wiki maintainer. When given a source document:
1. {ingest_or_update} wiki pages as needed (summaries, entity pages, concept pages).
2. Output EVERY file change as a fenced block:
   ```wiki:{wiki_path}/page-name.md
   # Page Title
   ...content...
   ```
3. Always output an updated {wiki_path}/index.md in the same format.
4. Do NOT output {wiki_path}/log.md — it is managed automatically.
5. Do NOT embed images — they are stored in the docs wiki.
6. On the primary summary page for this source, include this line near the top:
   {docs_line}
""".strip()

_INGEST_ACTION = "Write or update"
_UPDATE_ACTION = "Update existing pages with new information from the re-ingested source; preserve content that is still accurate, correct outdated claims, and add new information"

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
    schema: str, index: str, filename: str, source_text: str,
    wiki_path: str = "wiki", existing_pages: str = "",
    docs_link: Optional[str] = None,
    is_update: bool = False,
) -> list[dict]:
    docs_line = (
        f"**Original document:** [[{docs_link}]]"
        if docs_link
        else "(no original document link available)"
    )
    instructions = _INGEST_INSTRUCTIONS_TEMPLATE.format(
        wiki_path=wiki_path,
        docs_line=docs_line,
        ingest_or_update=_UPDATE_ACTION if is_update else _INGEST_ACTION,
    )
    existing_label = (
        "Existing wiki pages (update these — preserve accurate content, correct outdated claims):"
        if is_update
        else "Existing wiki pages (update these if relevant, preserving their content):"
    )
    existing_section = (
        f"\n\n{existing_label}\n{existing_pages}"
        if existing_pages else ""
    )
    action_phrase = "Re-process this updated source and output all changed files." if is_update else "Process this source and output all file changes."
    return [
        {"role": "system", "content": f"{schema}\n\n{instructions}"},
        {
            "role": "user",
            "content": (
                f"Current {wiki_path}/index.md:\n{index}"
                f"{existing_section}\n\n"
                f"{'Updated' if is_update else 'New'} source ({filename}):\n{source_text}\n\n"
                f"{action_phrase}"
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
    model = f"{config.llm.provider}/{config.llm.model}" if config.llm.provider else config.llm.model
    kwargs: dict = {
        "model": model,
        "messages": messages,
    }
    if config.llm.base_url:
        kwargs["api_base"] = config.llm.base_url
    if config.llm.api_key:
        kwargs["api_key"] = config.llm.api_key
    response = litellm.completion(**kwargs)
    return response.choices[0].message.content
