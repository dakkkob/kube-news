"""Prefect flow: Ingest entries from all configured RSS feeds."""

from __future__ import annotations

import logging

from prefect import flow, task

from src.config import load_sources_config
from src.ingestion.rss_client import fetch_rss
from src.storage.dynamodb_client import item_exists, save_metadata
from src.storage.s3_client import save_item

logger = logging.getLogger(__name__)


@task(retries=2, retry_delay_seconds=60, log_prints=True)
def ingest_feed(url: str, name: str) -> int:
    """Fetch and store entries from a single RSS feed. Returns count of new items."""
    items = fetch_rss(url, name)

    new_count = 0
    for item in items:
        if item_exists(item["item_id"]):
            continue

        s3_key = save_item(item)
        save_metadata(item, s3_key=s3_key)
        new_count += 1

    print(f"RSS {name}: {new_count} new items (of {len(items)} fetched)")
    return new_count


@flow(name="ingest-rss-feeds", log_prints=True)
def ingest_rss_feeds() -> dict[str, int]:
    """Ingest entries from all configured RSS feeds."""
    config = load_sources_config()
    results: dict[str, int] = {}

    for feed_config in config.rss_feeds:
        new_count = ingest_feed(url=feed_config.url, name=feed_config.name)
        results[feed_config.name] = new_count

    total_new = sum(results.values())
    print(f"RSS ingestion complete: {total_new} new items across {len(results)} feeds")
    return results


if __name__ == "__main__":
    ingest_rss_feeds()
