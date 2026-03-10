"""Prefect flow: Ingest end-of-life data for tracked products."""

from __future__ import annotations

import logging

from prefect import flow, task

from src.config import load_sources_config
from src.ingestion.endoflife_client import fetch_product_cycles
from src.storage.dynamodb_client import item_exists, save_metadata
from src.storage.s3_client import save_item

logger = logging.getLogger(__name__)


@task(retries=2, retry_delay_seconds=60, log_prints=True)
def ingest_product(product: str) -> int:
    """Fetch and store EOL data for a single product. Returns count of new items."""
    items = fetch_product_cycles(product)

    new_count = 0
    for item in items:
        if item_exists(item["item_id"]):
            continue

        # Mark EOL items as deprecation-adjacent
        if item.get("is_eol"):
            item["is_deprecation"] = True
            item["label"] = "eol"

        s3_key = save_item(item)
        save_metadata(item, s3_key=s3_key)
        new_count += 1

    print(f"EOL {product}: {new_count} new cycles (of {len(items)} fetched)")
    return new_count


@flow(name="ingest-endoflife", log_prints=True)
def ingest_endoflife() -> dict[str, int]:
    """Ingest EOL data for all configured products."""
    config = load_sources_config()
    results: dict[str, int] = {}

    for eol_config in config.endoflife_products:
        new_count = ingest_product(product=eol_config.product)
        results[eol_config.product] = new_count

    total_new = sum(results.values())
    print(f"EOL ingestion complete: {total_new} new cycles across {len(results)} products")
    return results


if __name__ == "__main__":
    ingest_endoflife()
