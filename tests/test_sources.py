import pytest
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
    assert result.source_path == str(f)


def test_parse_md_file(tmp_path):
    f = tmp_path / "notes.md"
    f.write_text("# Title\ncontent")
    result = parse_source(str(f))
    assert result.filename == "notes.md"
    assert result.text == "# Title\ncontent"
    assert result.source_path == str(f)


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


def test_parse_pdf_uses_docling(tmp_path, monkeypatch):
    pdf_path = tmp_path / "paper.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n")

    class FakeDocument:
        def export_to_markdown(self):
            return "# Title\n\nConverted text"

    class FakeResult:
        document = FakeDocument()

    class FakeConverter:
        def convert(self, source):
            assert source == str(pdf_path)
            return FakeResult()

    monkeypatch.setattr("docling.document_converter.DocumentConverter", lambda **kwargs: FakeConverter())

    result = parse_source(str(pdf_path))

    assert isinstance(result, ParsedSource)
    assert result.filename == "paper.pdf"
    assert result.text == "# Title\n\nConverted text"
    assert result.images == []
    assert result.source_path == str(pdf_path)


@pytest.mark.parametrize("ext", ["docx", "doc"])
def test_parse_word_docs_uses_docling(tmp_path, monkeypatch, ext):
    path = tmp_path / f"paper.{ext}"
    path.write_bytes(b"fake document bytes")

    class FakeDocument:
        def export_to_markdown(self):
            return "# Word Title\n\nConverted word text"

    class FakeResult:
        document = FakeDocument()

    class FakeConverter:
        def convert(self, source):
            assert source == str(path)
            return FakeResult()

    monkeypatch.setattr("docling.document_converter.DocumentConverter", lambda **kwargs: FakeConverter())

    result = parse_source(str(path))

    assert isinstance(result, ParsedSource)
    assert result.filename == path.name
    assert result.text == "# Word Title\n\nConverted word text"
    assert result.images == []
    assert result.source_path == str(path)


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
