"""Client for the endoflife.date API — version EOL tracking."""

from __future__ import annotations

import hashlib
import logging
from datetime import UTC, datetime
from typing import Any

import httpx

logger = logging.getLogger(__name__)

BASE_URL = "https://endoflife.date/api"
TIMEOUT = 30.0


def _item_id(product: str, cycle: str) -> str:
    return hashlib.sha256(f"eol:{product}:{cycle}".encode()).hexdigest()


def fetch_product_cycles(product: str) -> list[dict[str, Any]]:
    """Fetch all release cycles for a product from endoflife.date.

    No authentication required. Returns one item per version cycle
    with EOL date, latest release, and support status.
    """
    url = f"{BASE_URL}/{product}.json"

    with httpx.Client(timeout=TIMEOUT) as client:
        response = client.get(url)
        response.raise_for_status()
        cycles = response.json()

    items = []
    for cycle in cycles:
        cycle_name = str(cycle.get("cycle", "unknown"))
        eol = cycle.get("eol", False)
        eol_date = eol if isinstance(eol, str) else None

        is_eol = False
        if isinstance(eol, bool):
            is_eol = eol
        elif isinstance(eol, str):
            try:
                is_eol = datetime.strptime(eol, "%Y-%m-%d").date() < datetime.now(UTC).date()
            except ValueError:
                is_eol = False

        item = {
            "item_id": _item_id(product, cycle_name),
            "source": f"eol/{product}",
            "source_type": "endoflife",
            "title": f"{product} {cycle_name}",
            "body": _build_summary(product, cycle),
            "url": f"https://endoflife.date/{product}",
            "cycle": cycle_name,
            "latest_version": cycle.get("latest", ""),
            "published_at": cycle.get("releaseDate", ""),
            "release_date": cycle.get("releaseDate", ""),
            "eol_date": eol_date,
            "is_eol": is_eol,
            "lts": cycle.get("lts", False),
            "fetched_at": datetime.now(UTC).isoformat(),
        }
        items.append(item)

    logger.info("Fetched %d cycles for %s from endoflife.date", len(items), product)
    return items


def _build_summary(product: str, cycle: dict[str, Any]) -> str:
    """Build a human-readable summary of a release cycle."""
    parts = [f"{product} {cycle.get('cycle', '?')}"]

    latest = cycle.get("latest")
    if latest:
        parts.append(f"Latest: {latest}")

    release_date = cycle.get("releaseDate")
    if release_date:
        parts.append(f"Released: {release_date}")

    eol = cycle.get("eol")
    if isinstance(eol, bool):
        parts.append("EOL: Yes" if eol else "EOL: No")
    elif isinstance(eol, str):
        parts.append(f"EOL date: {eol}")

    lts = cycle.get("lts")
    if lts:
        parts.append("LTS: Yes")

    return " | ".join(parts)
