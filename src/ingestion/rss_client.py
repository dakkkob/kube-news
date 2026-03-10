"""RSS feed client for fetching blog posts and newsletters."""

from __future__ import annotations

import hashlib
import logging
from datetime import UTC, datetime
from typing import Any

import feedparser

logger = logging.getLogger(__name__)


def _item_id(source: str, unique_key: str) -> str:
    return hashlib.sha256(f"{source}:{unique_key}".encode()).hexdigest()


def _parse_date(entry: dict[str, Any]) -> str:
    """Extract and normalize published date from an RSS entry."""
    for field in ("published_parsed", "updated_parsed"):
        parsed = entry.get(field)
        if parsed:
            try:
                dt = datetime(*parsed[:6], tzinfo=UTC)
                return dt.isoformat()
            except (TypeError, ValueError):
                continue

    for field in ("published", "updated"):
        value = entry.get(field)
        if value:
            return value

    return datetime.now(UTC).isoformat()


def fetch_rss(url: str, name: str, max_entries: int = 50) -> list[dict[str, Any]]:
    """Fetch and normalize entries from an RSS/Atom feed.

    Returns items ready for S3 storage.
    """
    feed = feedparser.parse(url)

    if feed.get("bozo") and not feed.get("entries"):
        logger.error("Failed to parse RSS feed %s: %s", name, feed.get("bozo_exception"))
        return []

    items = []
    for entry in feed.get("entries", [])[:max_entries]:
        link = entry.get("link", "")
        title = entry.get("title", "Untitled")

        # Build the body from available content fields
        body = ""
        content = entry.get("content")
        if content:
            body = content[0].get("value", "") if isinstance(content, list) else ""
        elif entry.get("summary"):
            body = entry["summary"]
        elif entry.get("description"):
            body = entry["description"]

        item = {
            "item_id": _item_id(f"rss/{name}", link or title),
            "source": f"rss/{name}",
            "source_type": "rss",
            "title": title,
            "body": body,
            "url": link,
            "published_at": _parse_date(entry),
            "feed_name": name,
            "fetched_at": datetime.now(UTC).isoformat(),
        }
        items.append(item)

    logger.info("Fetched %d entries from RSS feed %s", len(items), name)
    return items
