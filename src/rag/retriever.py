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
FILTERED_CANDIDATES = 5
MIN_RELEVANCE_SCORE = 0.3

_RECENCY_KEYWORDS = frozenset(
    {
        "latest",
        "recent",
        "newest",
        "new",
        "current",
        "today",
        "this week",
        "this month",
        "last week",
        "last month",
    }
)

# Maps query keywords → Qdrant filter params for hybrid retrieval.
_INTENT_FILTERS: list[dict[str, Any]] = [
    {
        "keywords": ["cve", "vulnerability", "vulnerabilities", "security advisory"],
        "sources": ["cve/kubernetes"],
        "label": None,
    },
    {
        "keywords": ["deprecated", "deprecation", "removed", "eol", "end of life", "end-of-life"],
        "sources": [
            "rss/kubernetes-blog",
            "rss/lwkd",
            "eol/kubernetes",
            "eol/amazon-eks",
        ],
        "label": None,
    },
    {
        "keywords": ["security", "patch", "fixes"],
        "sources": ["cve/kubernetes"],
        "label": None,
    },
    {
        "keywords": ["kyverno", "cel policy", "cel policies"],
        "sources": ["rss/kyverno-blog", "eol/kyverno"],
        "label": None,
    },
]


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


def _detect_intent(query: str) -> dict[str, Any] | None:
    """Detect query intent and return Qdrant filter params, or None."""
    query_lower = query.lower()
    for intent in _INTENT_FILTERS:
        if any(kw in query_lower for kw in intent["keywords"]):
            return {"sources": intent["sources"], "label": intent["label"]}
    return None


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


def _enrich_hit(hit: dict[str, Any]) -> dict[str, Any]:
    """Fetch the full item from S3 and extract the body."""
    s3_key = hit.get("s3_key", "")
    body = ""
    extra_meta: dict[str, Any] = {}
    if s3_key:
        try:
            full_item = get_item(s3_key)
            body = full_item.get("body", "") or full_item.get("content", "") or ""
            # Carry structured metadata for thin-body items
            for key in ("cve_id", "cycle", "latest_version", "eol_date", "is_eol", "lts", "tag"):
                if key in full_item:
                    extra_meta[key] = full_item[key]
        except Exception:
            logger.warning("Failed to fetch S3 item: %s", s3_key)
    return {"body": body, **extra_meta}


def retrieve(query: str, top_k: int = 5) -> list[dict[str, Any]]:
    """Embed a query, search Qdrant, and enrich results with S3 full text.

    Uses hybrid retrieval: a primary semantic search plus an optional
    intent-filtered search that ensures relevant source types appear
    in the candidate pool.

    Returns a list of dicts with keys: item_id, source, title, url,
    published_at, label, score, body (plus optional structured metadata).
    """
    expanded = _expand_query(query)
    query_vector = embed_text(expanded)
    recency_weight = RECENCY_WEIGHT_BOOSTED if _is_recency_sensitive(query) else RECENCY_WEIGHT

    # Primary semantic search
    hits = qdrant_search(query_vector, limit=top_k * CANDIDATE_MULTIPLIER)

    # Hybrid: intent-filtered search to pull in relevant source types
    intent = _detect_intent(query)
    if intent:
        try:
            filtered_hits = qdrant_search(
                query_vector,
                limit=FILTERED_CANDIDATES,
                sources=intent.get("sources"),
                label=intent.get("label"),
            )
            # Merge — primary hits take priority, filtered fills gaps
            seen_in_primary = {h.get("item_id") for h in hits}
            for fh in filtered_hits:
                if fh.get("item_id") not in seen_in_primary:
                    hits.append(fh)
        except Exception:
            logger.warning("Filtered search failed (missing index?), using semantic only")

    results = []
    seen_ids: set[str] = set()
    for hit in hits:
        item_id = hit.get("item_id", "")
        if item_id in seen_ids:
            continue
        seen_ids.add(item_id)

        enriched = _enrich_hit(hit)

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
                **enriched,
            }
        )

    results.sort(key=lambda r: r["score"], reverse=True)
    results = [r for r in results if r["score"] >= MIN_RELEVANCE_SCORE]
    return results[:top_k]
