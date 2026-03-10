"""Client for Artifact Hub API — Helm chart updates."""

from __future__ import annotations

import hashlib
import logging
from datetime import UTC, datetime
from typing import Any

import httpx

logger = logging.getLogger(__name__)

BASE_URL = "https://artifacthub.io/api/v1"
TIMEOUT = 30.0


def _item_id(package_id: str, version: str) -> str:
    return hashlib.sha256(f"artifacthub:{package_id}:{version}".encode()).hexdigest()


def fetch_top_charts(
    kind: int = 0,
    sort: str = "stars",
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Fetch top Helm charts from Artifact Hub.

    No authentication required for public search.
    kind=0 means Helm charts.
    """
    url = f"{BASE_URL}/packages/search"
    params: dict[str, str | int] = {
        "kind": kind,
        "sort": sort,
        "limit": limit,
        "offset": 0,
    }

    with httpx.Client(timeout=TIMEOUT) as client:
        response = client.get(url, params=params)
        response.raise_for_status()
        data = response.json()

    packages = data.get("packages", [])
    items = []

    for pkg in packages:
        package_id = pkg.get("package_id", "")
        version = pkg.get("version", "")
        repo = pkg.get("repository", {})

        item = {
            "item_id": _item_id(package_id, version),
            "source": "artifacthub",
            "source_type": "helm_chart",
            "title": f"{pkg.get('name', 'unknown')} {version}",
            "body": pkg.get("description", ""),
            "url": (
                f"https://artifacthub.io/packages/helm/{repo.get('name', '')}/{pkg.get('name', '')}"
            ),
            "chart_name": pkg.get("name", ""),
            "chart_version": version,
            "app_version": pkg.get("app_version", ""),
            "repository": repo.get("name", ""),
            "stars": pkg.get("stars", 0),
            "published_at": pkg.get("created_at", ""),
            "fetched_at": datetime.now(UTC).isoformat(),
        }
        items.append(item)

    logger.info("Fetched %d Helm charts from Artifact Hub", len(items))
    return items
