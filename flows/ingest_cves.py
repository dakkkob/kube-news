"""Prefect flow: Ingest CVEs from the official Kubernetes CVE feed."""

from __future__ import annotations

import logging

from prefect import flow, task

from src.ingestion.cve_client import fetch_k8s_cves
from src.storage.dynamodb_client import item_exists, save_metadata
from src.storage.s3_client import save_item

logger = logging.getLogger(__name__)


@task(retries=2, retry_delay_seconds=60, log_prints=True)
def ingest_cve_feed() -> int:
    """Fetch and store CVEs. Returns count of new items."""
    items = fetch_k8s_cves()

    new_count = 0
    for item in items:
        if item_exists(item["item_id"]):
            continue

        # Mark CVEs as security items
        item["is_security"] = True
        item["label"] = "security"

        s3_key = save_item(item)
        save_metadata(item, s3_key=s3_key)
        new_count += 1

    print(f"CVE feed: {new_count} new items (of {len(items)} fetched)")
    return new_count


@flow(name="ingest-k8s-cves", log_prints=True)
def ingest_k8s_cves() -> int:
    """Ingest CVEs from the official Kubernetes CVE feed."""
    new_count = ingest_cve_feed()
    print(f"CVE ingestion complete: {new_count} new CVEs")
    return new_count


if __name__ == "__main__":
    ingest_k8s_cves()
