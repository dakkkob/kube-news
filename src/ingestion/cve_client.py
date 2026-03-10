"""Client for the official Kubernetes CVE feed."""

from __future__ import annotations

import hashlib
import logging
from datetime import UTC, datetime
from typing import Any

import httpx

logger = logging.getLogger(__name__)

K8S_CVE_FEED_URL = (
    "https://kubernetes.io/docs/reference/issues-security/official-cve-feed/index.json"
)
TIMEOUT = 30.0


def _item_id(cve_id: str) -> str:
    return hashlib.sha256(f"cve:{cve_id}".encode()).hexdigest()


def fetch_k8s_cves(url: str = K8S_CVE_FEED_URL) -> list[dict[str, Any]]:
    """Fetch CVEs from the official Kubernetes CVE JSON feed.

    No authentication required. The feed auto-refreshes within minutes
    of new CVE publications.
    """
    with httpx.Client(timeout=TIMEOUT) as client:
        response = client.get(url)
        response.raise_for_status()
        data = response.json()

    items_raw = data.get("items", [])
    items = []

    for cve in items_raw:
        cve_id = cve.get("id", "")
        external_url = cve.get("external_url", cve.get("url", ""))

        item = {
            "item_id": _item_id(cve_id),
            "source": "cve/kubernetes",
            "source_type": "cve",
            "title": cve.get("title", cve_id),
            "body": cve.get("content_text", cve.get("summary", "")),
            "url": external_url,
            "cve_id": cve_id,
            "published_at": cve.get("date_published", ""),
            "fetched_at": datetime.now(UTC).isoformat(),
        }
        items.append(item)

    logger.info("Fetched %d CVEs from Kubernetes CVE feed", len(items))
    return items
