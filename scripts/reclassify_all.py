"""One-off script: reclassify all items using local zero-shot BART-MNLI.

Downloads the model once, then classifies every DynamoDB item locally
(no HF API calls). Updates both DynamoDB labels and Qdrant payloads.

Usage on EC2:
    source .venv/bin/activate
    export $(grep -v '^#' .env | xargs)
    python scripts/reclassify_all.py
"""

from __future__ import annotations

import contextlib
import hashlib
import logging
import sys
import time
from pathlib import Path

# Ensure project root is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from transformers import pipeline  # noqa: E402

from src.processing.text_cleaner import build_document  # noqa: E402
from src.storage.dynamodb_client import (  # noqa: E402
    _get_table,
    update_processing_results,
)
from src.storage.s3_client import get_item  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# Same labels as the zero-shot classifier
CANDIDATE_LABELS = ["deprecation", "security", "feature", "release", "blog", "end of life"]
LABEL_MAP = {"end of life": "eol"}  # Normalize
THRESHOLD = 0.3


def _qdrant_point_id(item_id: str) -> int:
    """Deterministic Qdrant point ID (must match qdrant_client.py)."""
    return int(hashlib.sha256(item_id.encode()).hexdigest()[:16], 16)


def _scan_all_items() -> list[dict]:
    """Scan entire DynamoDB table."""
    table = _get_table()
    items: list[dict] = []
    scan_kwargs: dict = {}
    while True:
        response = table.scan(**scan_kwargs)
        items.extend(response.get("Items", []))
        if "LastEvaluatedKey" not in response:
            break
        scan_kwargs["ExclusiveStartKey"] = response["LastEvaluatedKey"]
    return items


def main() -> None:
    # 1. Load zero-shot model locally
    logger.info("Loading BART-MNLI model (first run downloads ~1.6GB)...")
    classifier = pipeline(
        "zero-shot-classification",
        model="facebook/bart-large-mnli",
        device=-1,  # CPU
    )
    logger.info("Model loaded.")

    # 2. Scan all DynamoDB items
    db_items = _scan_all_items()
    logger.info("Found %d items in DynamoDB", len(db_items))

    # 3. Try to connect to Qdrant (optional — updates payloads if available)
    qdrant_client = None
    try:
        from src.storage.qdrant_client import _get_client

        qdrant_client = _get_client()
        from src.config import QDRANT_COLLECTION

        logger.info("Connected to Qdrant — will update payloads too")
    except Exception:
        logger.warning("Qdrant not available — will only update DynamoDB")

    # 4. Classify each item
    classified = 0
    skipped = 0
    start = time.time()

    for i, db_item in enumerate(db_items):
        item_id = db_item["item_id"]
        s3_key = db_item.get("s3_key", "")

        # Load full item from S3
        full_item = dict(db_item)
        if s3_key:
            with contextlib.suppress(Exception):
                full_item = get_item(s3_key)

        # Build document text
        text = build_document(full_item)
        if not text.strip():
            skipped += 1
            continue

        # Classify
        result = classifier(text[:1500], CANDIDATE_LABELS, multi_label=False)
        top_label = result["labels"][0]
        top_score = result["scores"][0]

        # Normalize
        top_label = LABEL_MAP.get(top_label, top_label)
        if top_score < THRESHOLD:
            top_label = "unknown"

        is_deprecation = top_label == "deprecation"
        is_security = top_label == "security"

        # Update DynamoDB
        update_processing_results(
            item_id=item_id,
            label=top_label,
            confidence=top_score,
            is_deprecation=is_deprecation,
            is_security=is_security,
        )

        # Update Qdrant payload (label only, no re-embedding)
        if qdrant_client:
            try:
                point_id = _qdrant_point_id(item_id)
                qdrant_client.set_payload(
                    collection_name=QDRANT_COLLECTION,
                    payload={"label": top_label},
                    points=[point_id],
                )
            except Exception:
                pass  # Point may not exist in Qdrant yet

        classified += 1
        if (i + 1) % 50 == 0:
            elapsed = time.time() - start
            rate = classified / elapsed if elapsed > 0 else 0
            logger.info(
                "Progress: %d/%d classified (%.1f items/sec), %d skipped",
                classified,
                len(db_items),
                rate,
                skipped,
            )

    elapsed = time.time() - start
    logger.info(
        "Done! %d classified, %d skipped in %.0f seconds (%.1f items/sec)",
        classified,
        skipped,
        elapsed,
        classified / elapsed if elapsed > 0 else 0,
    )

    # 5. Print label distribution
    all_items = _scan_all_items()
    labels: dict[str, int] = {}
    for item in all_items:
        lbl = item.get("label", "unknown") or "unknown"
        labels[lbl] = labels.get(lbl, 0) + 1
    logger.info("Label distribution:")
    for lbl, count in sorted(labels.items(), key=lambda x: -x[1]):
        logger.info("  %s: %d", lbl, count)


if __name__ == "__main__":
    main()
