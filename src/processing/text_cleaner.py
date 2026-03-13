"""Clean raw text from ingested items for classification and embedding."""

from __future__ import annotations

import html
import re


def strip_html(text: str) -> str:
    """Remove HTML tags and decode entities."""
    text = re.sub(r"<[^>]+>", " ", text)
    return html.unescape(text)


def normalize_whitespace(text: str) -> str:
    """Collapse multiple spaces/newlines into single space."""
    return re.sub(r"\s+", " ", text).strip()


def clean_text(text: str, max_length: int = 2000) -> str:
    """Full cleaning pipeline: strip HTML, normalize, truncate."""
    text = strip_html(text)
    text = normalize_whitespace(text)
    if max_length and len(text) > max_length:
        text = text[:max_length]
    return text


def build_document(item: dict[str, str | None]) -> str:
    """Build a single text document from an item's title + body/content.

    This is the text that gets classified and embedded.
    """
    parts = []
    title = item.get("title", "") or ""
    if title:
        parts.append(title)

    body = item.get("body", "") or item.get("content", "") or item.get("description", "") or ""
    if body:
        parts.append(clean_text(body))

    return " ".join(parts) if parts else ""
