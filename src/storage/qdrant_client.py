"""Qdrant Cloud client for vector storage and similarity search."""

from __future__ import annotations

import logging
from typing import Any

from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    MatchValue,
    PayloadSchemaType,
    PointStruct,
    VectorParams,
)

from src.config import QDRANT_API_KEY, QDRANT_COLLECTION, QDRANT_URL
from src.processing.embedder import EMBEDDING_DIM

logger = logging.getLogger(__name__)

_client: QdrantClient | None = None


def _get_client() -> QdrantClient:
    global _client  # noqa: PLW0603
    if _client is None:
        if not QDRANT_URL:
            msg = "QDRANT_URL not set"
            raise ValueError(msg)
        _client = QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY or None)
    return _client


def ensure_collection() -> None:
    """Create the collection (and payload indexes) if it doesn't exist."""
    client = _get_client()
    collections = [c.name for c in client.get_collections().collections]
    if QDRANT_COLLECTION not in collections:
        client.create_collection(
            collection_name=QDRANT_COLLECTION,
            vectors_config=VectorParams(size=EMBEDDING_DIM, distance=Distance.COSINE),
        )
        logger.info("Created Qdrant collection: %s", QDRANT_COLLECTION)

    # Ensure keyword indexes exist for filtered search
    for field in ("source", "label"):
        client.create_payload_index(
            collection_name=QDRANT_COLLECTION,
            field_name=field,
            field_schema=PayloadSchemaType.KEYWORD,
        )
    logger.info("Ensured payload indexes on source, label")


def upsert_items(
    items: list[dict[str, Any]],
    vectors: list[list[float]],
) -> int:
    """Upsert items with their embedding vectors into Qdrant.

    Each item must have 'item_id'. Additional fields are stored as payload.
    Returns the number of points upserted.
    """
    client = _get_client()

    points = []
    for item, vector in zip(items, vectors, strict=True):
        payload = {
            "item_id": item["item_id"],
            "source": item.get("source", ""),
            "title": item.get("title", ""),
            "url": item.get("url", ""),
            "published_at": item.get("published_at", ""),
            "label": item.get("label", ""),
            "s3_key": item.get("s3_key", ""),
        }
        points.append(
            PointStruct(
                id=hash(item["item_id"]) % (2**63),  # Qdrant needs int or UUID
                vector=vector,
                payload=payload,
            )
        )

    if points:
        client.upsert(collection_name=QDRANT_COLLECTION, points=points)
        logger.info("Upserted %d points to Qdrant collection %s", len(points), QDRANT_COLLECTION)

    return len(points)


def search(
    query_vector: list[float],
    limit: int = 10,
    sources: list[str] | None = None,
    label: str | None = None,
) -> list[dict[str, Any]]:
    """Search for similar items by vector, optionally filtered by source or label.

    When both sources and label are given, items matching *any* condition are
    returned (OR / ``should`` logic).
    """
    client = _get_client()

    conditions: list[FieldCondition | Filter] = []
    if sources:
        for src in sources:
            conditions.append(FieldCondition(key="source", match=MatchValue(value=src)))
    if label:
        conditions.append(FieldCondition(key="label", match=MatchValue(value=label)))
    query_filter = Filter(should=conditions) if conditions else None  # type: ignore[arg-type]

    results = client.query_points(
        collection_name=QDRANT_COLLECTION,
        query=query_vector,
        query_filter=query_filter,
        limit=limit,
    )
    return [{**(point.payload or {}), "score": point.score} for point in results.points]


def scroll_vectors(limit: int = 500) -> list[list[float]]:
    """Scroll the collection and return raw vectors (for drift analysis)."""
    client = _get_client()
    vectors: list[list[float]] = []
    offset = None

    while len(vectors) < limit:
        batch_size = min(100, limit - len(vectors))
        results, next_offset = client.scroll(
            collection_name=QDRANT_COLLECTION,
            limit=batch_size,
            offset=offset,
            with_vectors=True,
        )
        for point in results:
            vec = point.vector
            if vec and isinstance(vec, list) and all(isinstance(v, float) for v in vec):
                vectors.append(vec)  # type: ignore[arg-type]
        if next_offset is None:
            break
        offset = next_offset

    return vectors
