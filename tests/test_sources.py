import pytest
import sys
import types
from pathlib import Path
from unittest.mock import patch, MagicMock
from llm_wiki.sources import parse_source, ParsedSource, chunk_text


def test_parse_text_file(tmp_path):
    f = tmp_path / "notes.txt"
    f.write_text("Hello world")
    result = parse_source(str(f))
    assert isinstance(result, ParsedSource)
    assert result.filename == "notes.txt"
    assert result.text == "Hello world"
    assert result.raw_bytes is None


def test_parse_md_file(tmp_path):
    f = tmp_path / "notes.md"
    f.write_text("# Title\ncontent")
    result = parse_source(str(f))
    assert result.filename == "notes.md"
    assert result.text == "# Title\ncontent"


def test_parse_url():
    mock_response = MagicMock()
    mock_response.text = "<html><body><p>Article content here.</p></body></html>"
    mock_response.content = b"<html>...</html>"
    mock_response.raise_for_status = MagicMock()

    with patch("httpx.get", return_value=mock_response):
        result = parse_source("https://example.com/article")

    assert "example" in result.filename
    assert ".html" in result.filename
    assert "Article content here" in result.text
    assert result.raw_bytes == b"<html>...</html>"


def test_parse_url_fetch_error():
    import httpx
    with patch("httpx.get", side_effect=httpx.ConnectError("refused")):
        with pytest.raises(httpx.ConnectError):
            parse_source("https://example.com/article")


def test_parse_pdf_uses_opendataloader(tmp_path, monkeypatch):
    pdf_path = tmp_path / "paper.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n")

    def fake_convert(*, input_path, output_dir, **kwargs):
        assert input_path == [str(pdf_path)]
        assert kwargs["format"] == "markdown"
        assert kwargs["image_output"] == "off"
        assert kwargs["use_struct_tree"] is True
        assert kwargs["quiet"] is True
        output = Path(output_dir) / "paper.md"
        output.write_text("# Title\n\nConverted text")

    fake_module = types.ModuleType("opendataloader_pdf")
    fake_module.convert = fake_convert
    monkeypatch.setitem(sys.modules, "opendataloader_pdf", fake_module)

    result = parse_source(str(pdf_path))

    assert isinstance(result, ParsedSource)
    assert result.filename == "paper.pdf"
    assert result.text == "# Title\n\nConverted text"
    assert result.images == []


def test_chunk_text_short():
    text = "short text"
    assert chunk_text(text, max_chars=100) == ["short text"]


def test_chunk_text_long():
    text = "a" * 150
    chunks = chunk_text(text, max_chars=100)
    assert len(chunks) == 2
    assert chunks[0] == "a" * 100
    assert chunks[1] == "a" * 50


def test_chunk_text_exact():
    text = "a" * 100
    assert chunk_text(text, max_chars=100) == ["a" * 100]
