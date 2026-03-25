"""DynamoDB client for metadata storage and deduplication."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

import boto3
from boto3.dynamodb.conditions import Attr, Key

from src.config import AWS_REGION, DRIFT_METRICS_TABLE, DYNAMODB_TABLE

logger = logging.getLogger(__name__)


def _get_table() -> Any:
    dynamodb = boto3.resource("dynamodb", region_name=AWS_REGION)
    return dynamodb.Table(DYNAMODB_TABLE)


def _get_drift_table() -> Any:
    dynamodb = boto3.resource("dynamodb", region_name=AWS_REGION)
    return dynamodb.Table(DRIFT_METRICS_TABLE)


def item_exists(item_id: str) -> bool:
    """Check if an item already exists in DynamoDB (dedup check)."""
    table = _get_table()
    response = table.get_item(
        Key={"item_id": item_id},
        ProjectionExpression="item_id",
    )
    return "Item" in response


def save_metadata(item: dict[str, Any], s3_key: str = "") -> None:
    """Save item metadata to DynamoDB.

    Stores structured metadata (not full text) for querying.
    Full text lives in S3.
    """
    table = _get_table()

    db_item: dict[str, Any] = {
        "item_id": item["item_id"],
        "source": item.get("source", "unknown"),
        "source_type": item.get("source_type", "unknown"),
        "title": item.get("title", ""),
        "url": item.get("url", ""),
        "published_at": item.get("published_at") or datetime.now(UTC).isoformat(),
        "fetched_at": item.get("fetched_at") or datetime.now(UTC).isoformat(),
        "s3_key": s3_key,
        # Classification fields (populated in Phase 2)
        "label": item.get("label", ""),
        "confidence": str(item.get("confidence", "")),
        "is_deprecation": str(item.get("is_deprecation", False)).lower(),
        "is_security": str(item.get("is_security", False)).lower(),
    }

    # Add source-specific fields
    if item.get("cve_id"):
        db_item["cve_id"] = item["cve_id"]
    if item.get("tag"):
        db_item["tag"] = item["tag"]
    if item.get("cycle"):
        db_item["cycle"] = item["cycle"]
    if item.get("is_eol") is not None:
        db_item["is_eol"] = item["is_eol"]
    if item.get("eol_date"):
        db_item["eol_date"] = item["eol_date"]

    table.put_item(Item=db_item)
    logger.debug("Saved metadata for item %s", item["item_id"])


def query_by_source(source: str, limit: int = 100) -> list[dict[str, Any]]:
    """Query items by source."""
    table = _get_table()
    response = table.query(
        IndexName="source-published_at-index",
        KeyConditionExpression=Key("source").eq(source),
        ScanIndexForward=False,
        Limit=limit,
    )
    result: list[dict[str, Any]] = response.get("Items", [])
    return result


def query_deprecations(limit: int = 50) -> list[dict[str, Any]]:
    """Query items flagged as deprecations, sorted by date."""
    table = _get_table()
    response = table.scan(
        FilterExpression=Attr("is_deprecation").eq("true"),
        Limit=limit,
    )
    items: list[dict[str, Any]] = response.get("Items", [])
    items.sort(key=lambda x: x.get("published_at", ""), reverse=True)
    return items


def query_security(limit: int = 50) -> list[dict[str, Any]]:
    """Query items flagged as security issues."""
    table = _get_table()
    response = table.scan(
        FilterExpression=Attr("is_security").eq("true"),
        Limit=limit,
    )
    items: list[dict[str, Any]] = response.get("Items", [])
    items.sort(key=lambda x: x.get("published_at", ""), reverse=True)
    return items


def query_unprocessed(limit: int = 100) -> list[dict[str, Any]]:
    """Query items that haven't been classified yet (label is empty)."""
    table = _get_table()
    response = table.scan(
        FilterExpression=Attr("label").eq("") | Attr("label").not_exists(),
        Limit=limit,
    )
    items: list[dict[str, Any]] = response.get("Items", [])
    return items


def update_processing_results(
    item_id: str,
    label: str,
    confidence: float,
    is_deprecation: bool,
    is_security: bool,
    entities: dict[str, Any] | None = None,
) -> None:
    """Update an item with classification and entity extraction results."""
    table = _get_table()
    update_expr = "SET #lbl = :label, confidence = :conf, is_deprecation = :dep, is_security = :sec"
    expr_values: dict[str, Any] = {
        ":label": label,
        ":conf": str(round(confidence, 4)),
        ":dep": str(is_deprecation).lower(),
        ":sec": str(is_security).lower(),
    }
    expr_names = {"#lbl": "label"}

    if entities:
        update_expr += ", entities = :ent"
        expr_values[":ent"] = entities

    table.update_item(
        Key={"item_id": item_id},
        UpdateExpression=update_expr,
        ExpressionAttributeValues=expr_values,
        ExpressionAttributeNames=expr_names,
    )
    logger.debug("Updated processing results for item %s", item_id)


def query_recent(days: int = 30, limit: int = 100) -> list[dict[str, Any]]:
    """Query recently ingested items."""
    table = _get_table()
    cutoff = datetime.now(UTC).isoformat()
    response = table.scan(
        FilterExpression=Attr("fetched_at").lte(cutoff),
        Limit=limit,
    )
    items: list[dict[str, Any]] = response.get("Items", [])
    items.sort(key=lambda x: x.get("published_at", ""), reverse=True)
    return items


# ---------------------------------------------------------------------------
# Drift metrics table
# ---------------------------------------------------------------------------


def save_drift_metric(check_type: str, timestamp: str, metrics: dict[str, Any]) -> None:
    """Save a drift check result to the drift-metrics table."""
    table = _get_drift_table()
    item: dict[str, Any] = {
        "check_type": check_type,
        "timestamp": timestamp,
        **{k: str(v) if isinstance(v, (float, int, bool)) else v for k, v in metrics.items()},
    }
    table.put_item(Item=item)
    logger.debug("Saved drift metric: %s @ %s", check_type, timestamp)


def query_drift_metrics(check_type: str, limit: int = 30) -> list[dict[str, Any]]:
    """Query drift metrics by check_type, most recent first."""
    table = _get_drift_table()
    response = table.query(
        KeyConditionExpression=Key("check_type").eq(check_type),
        ScanIndexForward=False,
        Limit=limit,
    )
    result: list[dict[str, Any]] = response.get("Items", [])
    return result


def get_drift_baseline(check_type: str) -> dict[str, Any] | None:
    """Get the stored baseline for a given check type."""
    table = _get_drift_table()
    response = table.get_item(
        Key={"check_type": f"{check_type}_baseline", "timestamp": "baseline"},
    )
    item: dict[str, Any] | None = response.get("Item")
    return item


def save_drift_baseline(check_type: str, baseline: dict[str, Any]) -> None:
    """Save or overwrite a drift baseline."""
    table = _get_drift_table()
    item: dict[str, Any] = {
        "check_type": f"{check_type}_baseline",
        "timestamp": "baseline",
        **{k: str(v) if isinstance(v, (float, int, bool)) else v for k, v in baseline.items()},
    }
    table.put_item(Item=item)
    logger.debug("Saved drift baseline: %s", check_type)


def query_classified_items(
    days: int = 7,
    min_confidence: float = 0.0,
    limit: int = 500,
) -> list[dict[str, Any]]:
    """Query items classified within the last N days.

    Returns items with a non-empty label and confidence above min_confidence.
    Paginates through the full scan to collect up to *limit* results.
    """
    from datetime import timedelta

    table = _get_table()
    cutoff = (datetime.now(UTC) - timedelta(days=days)).isoformat()

    filter_expr = Attr("label").exists() & Attr("label").ne("") & Attr("fetched_at").gte(cutoff)

    items: list[dict[str, Any]] = []
    scan_kwargs: dict[str, Any] = {"FilterExpression": filter_expr}

    while len(items) < limit:
        response = table.scan(**scan_kwargs)
        batch: list[dict[str, Any]] = response.get("Items", [])
        for item in batch:
            conf = float(item.get("confidence", "0") or "0")
            if conf >= min_confidence:
                items.append(item)
                if len(items) >= limit:
                    break
        if "LastEvaluatedKey" not in response:
            break
        scan_kwargs["ExclusiveStartKey"] = response["LastEvaluatedKey"]

    return items
