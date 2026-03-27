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


_STOPWORDS = frozenset(
    [
        "a",
        "an",
        "the",
        "is",
        "are",
        "was",
        "were",
        "be",
        "been",
        "being",
        "have",
        "has",
        "had",
        "do",
        "does",
        "did",
        "will",
        "would",
        "shall",
        "should",
        "may",
        "might",
        "can",
        "could",
        "to",
        "of",
        "in",
        "for",
        "on",
        "with",
        "at",
        "by",
        "from",
        "as",
        "into",
        "about",
        "between",
        "through",
        "and",
        "or",
        "but",
        "not",
        "no",
        "it",
        "its",
    ]
)


def _query_keywords(query: str) -> set[str]:
    """Extract meaningful keywords from a query string."""
    return {w.lower().strip("?.,!:;") for w in query.split()} - _STOPWORDS


def extract_relevant_snippet(body: str, query: str, max_length: int = 1500) -> str:
    """Extract the most query-relevant section of body text.

    Splits the cleaned body into sentences, scores each by keyword overlap
    with the query, and returns the best contiguous window that fits within
    max_length. Falls back to the first max_length chars if no keywords match.
    """
    cleaned = strip_html(body)
    cleaned = normalize_whitespace(cleaned)
    if len(cleaned) <= max_length:
        return cleaned

    keywords = _query_keywords(query)
    if not keywords:
        return cleaned[:max_length]

    # Split into sentences
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", cleaned) if s.strip()]
    if not sentences:
        return cleaned[:max_length]

    # Score each sentence by keyword overlap
    scores = []
    for s in sentences:
        words = {w.lower().strip("?.,!:;") for w in s.split()}
        scores.append(len(words & keywords))

    # Find best-scoring contiguous window that fits max_length
    best_start, best_score, best_end = 0, 0, 0
    win_start, win_len, win_score = 0, 0, 0

    for i, s in enumerate(sentences):
        added_len = len(s) + (2 if win_len > 0 else 0)
        while win_start < i and win_len + added_len > max_length:
            win_len -= len(sentences[win_start]) + (2 if win_start < i - 1 else 0)
            win_score -= scores[win_start]
            win_start += 1
        win_len += added_len
        win_score += scores[i]
        if win_score > best_score:
            best_score = win_score
            best_start = win_start
            best_end = i + 1

    if best_score == 0:
        return cleaned[:max_length]

    return " ".join(sentences[best_start:best_end])[:max_length]


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
