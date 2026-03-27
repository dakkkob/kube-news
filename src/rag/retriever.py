"""Retrieve relevant items from Qdrant and fetch full text from S3."""

from __future__ import annotations

import logging
import math
from datetime import UTC, datetime
from typing import Any

from src.processing.embedder import embed_text
from src.storage.qdrant_client import search as qdrant_search
from src.storage.s3_client import get_item

logger = logging.getLogger(__name__)

RECENCY_WEIGHT = 0.1
RECENCY_WEIGHT_BOOSTED = 0.4
RECENCY_HALF_LIFE_DAYS = 90
CANDIDATE_MULTIPLIER = 4
MIN_RELEVANCE_SCORE = 0.3

_RECENCY_KEYWORDS = frozenset({
    "latest", "recent", "newest", "new", "current",
    "today", "this week", "this month", "last week", "last month",
})


def _is_recency_sensitive(query: str) -> bool:
    """Check if a query is asking for recent/latest information."""
    query_lower = query.lower()
    return any(kw in query_lower for kw in _RECENCY_KEYWORDS)


def _expand_query(query: str) -> str:
    """Light query expansion for better embedding matching."""
    q = query.strip()
    if len(q.split()) <= 3:
        q = f"Kubernetes {q}"
    return q


def _recency_score(published_at: str) -> float:
    """Compute a 0-1 recency score using exponential decay.

    Items published today score ~1.0; items one half-life old score ~0.5.
    """
    if not published_at:
        return 0.0
    try:
        pub_date = datetime.fromisoformat(published_at.replace("Z", "+00:00"))
        if pub_date.tzinfo is None:
            pub_date = pub_date.replace(tzinfo=UTC)
        age_days = max((datetime.now(UTC) - pub_date).days, 0)
        return math.exp(-math.log(2) * age_days / RECENCY_HALF_LIFE_DAYS)
    except (ValueError, TypeError):
        return 0.0


def retrieve(query: str, top_k: int = 5) -> list[dict[str, Any]]:
    """Embed a query, search Qdrant, and enrich results with S3 full text.

    Fetches extra candidates and re-ranks using a weighted blend of
    semantic similarity and recency before returning the top_k results.

    Returns a list of dicts with keys: item_id, source, title, url,
    published_at, label, score, body.
    """
    expanded = _expand_query(query)
    query_vector = embed_text(expanded)
    hits = qdrant_search(query_vector, limit=top_k * CANDIDATE_MULTIPLIER)
    recency_weight = RECENCY_WEIGHT_BOOSTED if _is_recency_sensitive(query) else RECENCY_WEIGHT

    results = []
    seen_ids: set[str] = set()
    for hit in hits:
        # Dedup by item_id (same item may have multiple vectors in Qdrant)
        item_id = hit.get("item_id", "")
        if item_id in seen_ids:
            continue
        seen_ids.add(item_id)

        s3_key = hit.get("s3_key", "")
        body = ""
        if s3_key:
            try:
                full_item = get_item(s3_key)
                body = full_item.get("body", "") or full_item.get("content", "") or ""
            except Exception:
                logger.warning("Failed to fetch S3 item: %s", s3_key)

        published_at = hit.get("published_at", "")
        similarity = hit.get("score", 0.0)
        recency = _recency_score(published_at)
        combined = similarity * (1 - recency_weight) + recency * recency_weight

        results.append(
            {
                "item_id": item_id,
                "source": hit.get("source", ""),
                "title": hit.get("title", ""),
                "url": hit.get("url", ""),
                "published_at": published_at,
                "label": hit.get("label", ""),
                "score": round(combined, 4),
                "body": body,
            }
        )

    results.sort(key=lambda r: r["score"], reverse=True)
    # Filter out low-relevance noise
    results = [r for r in results if r["score"] >= MIN_RELEVANCE_SCORE]
    return results[:top_k]
