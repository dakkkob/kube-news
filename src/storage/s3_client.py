"""S3 client for partitioned raw data storage."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Any

import boto3

from src.config import AWS_REGION, S3_BUCKET

logger = logging.getLogger(__name__)


def _get_client() -> Any:
    return boto3.client("s3", region_name=AWS_REGION)


def _build_key(source: str, item_id: str, published_at: str = "") -> str:
    """Build a partitioned S3 key: {source}/{year}/{month}/{day}/{item_id}.json"""
    if published_at:
        try:
            dt = datetime.fromisoformat(published_at.replace("Z", "+00:00"))
        except ValueError:
            dt = datetime.now(UTC)
    else:
        dt = datetime.now(UTC)

    return f"{source}/{dt.year}/{dt.month:02d}/{dt.day:02d}/{item_id}.json"


def save_item(item: dict[str, Any], bucket: str = S3_BUCKET) -> str:
    """Save a single item to S3 as JSON.

    Returns the S3 key where the item was stored.
    """
    source = item.get("source", "unknown")
    item_id = item.get("item_id", "unknown")
    published_at = item.get("published_at", "")

    key = _build_key(source, item_id, published_at)

    client = _get_client()
    client.put_object(
        Bucket=bucket,
        Key=key,
        Body=json.dumps(item, ensure_ascii=False, default=str),
        ContentType="application/json",
    )

    logger.debug("Saved item %s to s3://%s/%s", item_id, bucket, key)
    return key


def save_items(items: list[dict[str, Any]], bucket: str = S3_BUCKET) -> list[str]:
    """Save multiple items to S3. Returns list of S3 keys."""
    keys = []
    for item in items:
        key = save_item(item, bucket)
        keys.append(key)
    logger.info("Saved %d items to s3://%s", len(keys), bucket)
    return keys


def get_item(key: str, bucket: str = S3_BUCKET) -> dict[str, Any]:
    """Retrieve a single item from S3 by key."""
    client = _get_client()
    response = client.get_object(Bucket=bucket, Key=key)
    body = response["Body"].read().decode("utf-8")
    return json.loads(body)
