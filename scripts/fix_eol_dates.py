"""One-off script: backfill published_at on EOL items from endoflife.date API.

Existing EOL items in DynamoDB have published_at set to their ingestion date
(datetime.now at fetch time) instead of the actual release date. This script
fetches the real releaseDate from the API and updates DynamoDB.

Usage on EC2 (or locally with AWS credentials):
    source .venv/bin/activate
    export $(grep -v '^#' .env | xargs)
    python scripts/fix_eol_dates.py
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from boto3.dynamodb.conditions import Attr  # noqa: E402

from src.storage.dynamodb_client import _get_table, _paginated_scan  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

API_BASE = "https://endoflife.date/api"


def _fetch_release_dates(product: str) -> dict[str, str]:
    """Fetch cycle → releaseDate mapping from endoflife.date API."""
    url = f"{API_BASE}/{product}.json"
    with httpx.Client(timeout=30.0) as client:
        response = client.get(url)
        response.raise_for_status()
        cycles = response.json()
    return {str(c.get("cycle", "")): c.get("releaseDate", "") for c in cycles}


def main() -> None:
    # 1. Scan all EOL items from DynamoDB
    items = _paginated_scan(Attr("source").begins_with("eol/"), limit=5000)
    logger.info("Found %d EOL items in DynamoDB", len(items))

    if not items:
        return

    # 2. Group by product
    by_product: dict[str, list[dict]] = {}
    for item in items:
        product = item["source"].removeprefix("eol/")
        by_product.setdefault(product, []).append(item)

    # 3. For each product, fetch release dates and update
    table = _get_table()
    updated = 0
    skipped = 0

    for product, product_items in by_product.items():
        try:
            release_dates = _fetch_release_dates(product)
        except Exception:
            logger.warning("Failed to fetch release dates for %s, skipping", product)
            skipped += len(product_items)
            continue

        for item in product_items:
            cycle = item.get("cycle", "")
            release_date = release_dates.get(cycle, "")

            if not release_date:
                skipped += 1
                continue

            current_published = item.get("published_at", "")
            if current_published.startswith(release_date):
                skipped += 1
                continue  # Already correct

            table.update_item(
                Key={"item_id": item["item_id"]},
                UpdateExpression="SET published_at = :pub",
                ExpressionAttributeValues={":pub": release_date},
            )
            updated += 1

        logger.info(
            "%s: updated %d/%d items",
            product,
            sum(1 for i in product_items if release_dates.get(i.get("cycle", ""))),
            len(product_items),
        )

    logger.info("Done! Updated %d items, skipped %d", updated, skipped)


if __name__ == "__main__":
    main()
