"""Tests for text cleaning utilities."""

from src.processing.text_cleaner import build_document, clean_text, normalize_whitespace, strip_html


def test_strip_html_removes_tags():
    result = strip_html("<p>hello <b>world</b></p>")
    assert "<p>" not in result
    assert "<b>" not in result
    assert "hello" in result
    assert "world" in result


def test_strip_html_decodes_entities():
    assert "a & b" in strip_html("a &amp; b")


def test_normalize_whitespace():
    assert normalize_whitespace("  hello   world  \n\n  foo  ") == "hello world foo"


def test_clean_text_full_pipeline():
    raw = "<p>Hello   <b>World</b></p>\n\n  Extra  spaces  "
    result = clean_text(raw)
    assert "Hello" in result
    assert "World" in result
    assert "<p>" not in result
    assert "\n" not in result


def test_clean_text_truncates():
    long_text = "x" * 3000
    result = clean_text(long_text, max_length=100)
    assert len(result) == 100


def test_build_document_title_and_body():
    item = {"title": "K8s 1.31 Released", "body": "New features include..."}
    doc = build_document(item)
    assert "K8s 1.31 Released" in doc
    assert "New features include" in doc


def test_build_document_title_only():
    item = {"title": "Just a Title"}
    doc = build_document(item)
    assert doc == "Just a Title"


def test_build_document_empty():
    assert build_document({}) == ""
    assert build_document({"title": "", "body": ""}) == ""


def test_build_document_uses_content_fallback():
    item = {"title": "Title", "content": "<p>HTML content</p>"}
    doc = build_document(item)
    assert "Title" in doc
    assert "HTML content" in doc
    assert "<p>" not in doc
