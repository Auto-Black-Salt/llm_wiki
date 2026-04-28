import pytest
from unittest.mock import MagicMock, patch
from llm_wiki.config import Config, LLMConfig, PathsConfig
from llm_wiki.llm import (
    build_ingest_messages,
    build_query_step1_messages,
    build_query_step2_messages,
    build_lint_messages,
    parse_relevant_pages,
    strip_image_markdown,
    call_llm,
)


@pytest.fixture
def config():
    return Config(
        llm=LLMConfig(
            provider="openai",
            model="local-model",
            base_url="http://localhost:1234/v1",
            api_key="lm-studio",
        ),
        paths=PathsConfig(raw="raw", wiki="wiki", schema="schema.md"),
    )


def test_build_ingest_messages():
    messages = build_ingest_messages(
        schema="wiki conventions",
        index="## Pages\n- page1",
        filename="article.md",
        source_text="Some article text",
    )
    assert len(messages) == 2
    assert messages[0]["role"] == "system"
    assert "wiki conventions" in messages[0]["content"]
    assert messages[1]["role"] == "user"
    assert "article.md" in messages[1]["content"]
    assert "Some article text" in messages[1]["content"]
    assert "## Pages" in messages[1]["content"]
    assert "information-dense" in messages[0]["content"]


def test_build_query_step1_messages():
    messages = build_query_step1_messages(
        schema="wiki conventions",
        index="## Pages\n- page1",
        question="What is X?",
    )
    assert messages[1]["role"] == "user"
    assert "What is X?" in messages[1]["content"]
    assert "## Pages" in messages[1]["content"]


def test_build_query_step2_messages():
    messages = build_query_step2_messages(
        schema="wiki conventions",
        pages="# Page 1\ncontent about X",
        question="What is X?",
    )
    assert "What is X?" in messages[1]["content"]
    assert "# Page 1" in messages[1]["content"]


def test_build_lint_messages():
    messages = build_lint_messages(
        schema="wiki conventions",
        pages="# Page 1\ncontent\n# Page 2\ncontent",
    )
    assert "# Page 1" in messages[1]["content"]
    assert "contradictions" in messages[1]["content"].lower()


def test_parse_relevant_pages():
    response = "```relevant_pages\nwiki/page1.md\nwiki/page2.md\n```"
    pages = parse_relevant_pages(response)
    assert pages == ["wiki/page1.md", "wiki/page2.md"]


def test_parse_relevant_pages_empty():
    assert parse_relevant_pages("No blocks here") == []


def test_parse_relevant_pages_blank_lines():
    response = "```relevant_pages\nwiki/page1.md\n\nwiki/page2.md\n```"
    pages = parse_relevant_pages(response)
    assert pages == ["wiki/page1.md", "wiki/page2.md"]


def test_strip_image_markdown():
    text = "# Title\n\nText ![Figure](assets/doc/figure.png) more text."
    cleaned = strip_image_markdown(text)
    assert "![Figure]" not in cleaned
    assert "Text" in cleaned
    assert "more text" in cleaned


def test_call_llm(config):
    mock_response = MagicMock()
    mock_response.choices[0].message.content = "response text"
    with patch("litellm.completion", return_value=mock_response) as mock_completion:
        result = call_llm(config, [{"role": "user", "content": "test"}])
    assert result == "response text"
    call_kwargs = mock_completion.call_args.kwargs
    assert call_kwargs["model"] == "openai/local-model"
    assert call_kwargs["api_base"] == "http://localhost:1234/v1"
    assert call_kwargs["api_key"] == "lm-studio"


def test_call_llm_no_base_url(config):
    config.llm.base_url = ""
    mock_response = MagicMock()
    mock_response.choices[0].message.content = "ok"
    with patch("litellm.completion", return_value=mock_response) as mock_completion:
        call_llm(config, [{"role": "user", "content": "test"}])
    call_kwargs = mock_completion.call_args.kwargs
    assert "api_base" not in call_kwargs
