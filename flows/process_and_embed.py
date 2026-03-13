"""Prefect flow: Process unprocessed items — classify, extract entities, embed, upsert to Qdrant."""

from __future__ import annotations

import logging

from prefect import flow, task

from src.processing.classifier import classify_text
from src.processing.embedder import embed_batch
from src.processing.entity_extractor import extract_entities
from src.processing.text_cleaner import build_document
from src.storage.dynamodb_client import query_unprocessed, update_processing_results
from src.storage.qdrant_client import ensure_collection, upsert_items
from src.storage.s3_client import get_item

logger = logging.getLogger(__name__)

BATCH_SIZE = 20


@task(retries=1, retry_delay_seconds=30, log_prints=True)
def fetch_unprocessed(limit: int = 100) -> list[dict]:
    """Get items from DynamoDB that haven't been classified yet."""
    items = query_unprocessed(limit=limit)
    print(f"Found {len(items)} unprocessed items")
    return items


@task(retries=1, retry_delay_seconds=30, log_prints=True)
def load_full_items(db_items: list[dict]) -> list[dict]:
    """Load full item data from S3 for items that have an s3_key."""
    full_items = []
    for db_item in db_items:
        s3_key = db_item.get("s3_key", "")
        if s3_key:
            try:
                full_item = get_item(s3_key)
                # Carry over DB fields not in S3
                full_item["s3_key"] = s3_key
                full_items.append(full_item)
            except Exception:
                logger.warning("Failed to load S3 item: %s", s3_key)
                # Fall back to DB metadata only
                full_items.append(db_item)
        else:
            full_items.append(db_item)

    print(f"Loaded {len(full_items)} items from S3")
    return full_items


@task(retries=2, retry_delay_seconds=60, log_prints=True)
def classify_items(items: list[dict]) -> list[dict]:
    """Classify each item using zero-shot BART-MNLI."""
    for item in items:
        doc = build_document(item)
        if not doc:
            item["label"] = "unknown"
            item["confidence"] = 0.0
            continue

        result = classify_text(doc)
        item["label"] = result["label"]
        item["confidence"] = result["confidence"]

    classified = sum(1 for i in items if i.get("label") not in ("unknown", ""))
    print(f"Classified {classified}/{len(items)} items")
    return items


@task(log_prints=True)
def extract_all_entities(items: list[dict]) -> list[dict]:
    """Extract K8s entities from each item."""
    for item in items:
        doc = build_document(item)
        if doc:
            item["entities"] = extract_entities(doc)
    print(f"Extracted entities from {len(items)} items")
    return items


@task(retries=1, retry_delay_seconds=30, log_prints=True)
def embed_and_upsert(items: list[dict]) -> int:
    """Embed items and upsert to Qdrant."""
    ensure_collection()

    docs = [build_document(item) or item.get("title", "") for item in items]

    # Process in batches
    total_upserted = 0
    for i in range(0, len(items), BATCH_SIZE):
        batch_items = items[i : i + BATCH_SIZE]
        batch_docs = docs[i : i + BATCH_SIZE]

        vectors = embed_batch(batch_docs)
        upserted = upsert_items(batch_items, vectors)
        total_upserted += upserted

    print(f"Embedded and upserted {total_upserted} items to Qdrant")
    return total_upserted


@task(log_prints=True)
def update_dynamo_labels(items: list[dict]) -> int:
    """Write classification + entity results back to DynamoDB."""
    updated = 0
    for item in items:
        label = item.get("label", "unknown")
        confidence = float(item.get("confidence", 0.0))
        is_dep = label == "deprecation"
        is_sec = label == "security"
        entities = item.get("entities")

        update_processing_results(
            item_id=item["item_id"],
            label=label,
            confidence=confidence,
            is_deprecation=is_dep,
            is_security=is_sec,
            entities=entities,
        )
        updated += 1

    print(f"Updated {updated} items in DynamoDB")
    return updated


@flow(name="process-and-embed", log_prints=True)
def process_and_embed(limit: int = 100) -> dict[str, int]:
    """Main processing pipeline: classify, extract entities, embed, store."""
    db_items = fetch_unprocessed(limit=limit)

    if not db_items:
        print("No unprocessed items found. Nothing to do.")
        return {"processed": 0, "upserted": 0}

    items = load_full_items(db_items)
    items = classify_items(items)
    items = extract_all_entities(items)

    upserted = embed_and_upsert(items)
    updated = update_dynamo_labels(items)

    print(f"Processing complete: {updated} classified, {upserted} upserted to Qdrant")
    return {"processed": updated, "upserted": upserted}


if __name__ == "__main__":
    process_and_embed()
