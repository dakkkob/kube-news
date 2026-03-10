"""GitHub API client for fetching releases and KEP content."""

from __future__ import annotations

import hashlib
import logging
from datetime import UTC, datetime
from typing import Any

import httpx

from src.config import GITHUB_TOKEN

logger = logging.getLogger(__name__)

BASE_URL = "https://api.github.com"
TIMEOUT = 30.0


def _headers() -> dict[str, str]:
    headers = {"Accept": "application/vnd.github+json"}
    if GITHUB_TOKEN:
        headers["Authorization"] = f"Bearer {GITHUB_TOKEN}"
    return headers


def _item_id(source: str, unique_key: str) -> str:
    return hashlib.sha256(f"{source}:{unique_key}".encode()).hexdigest()


def fetch_releases(owner: str, repo: str, per_page: int = 30) -> list[dict[str, Any]]:
    """Fetch releases from a GitHub repository.

    Returns normalized items ready for S3 storage.
    """
    url = f"{BASE_URL}/repos/{owner}/{repo}/releases"
    items = []

    with httpx.Client(timeout=TIMEOUT, headers=_headers()) as client:
        response = client.get(url, params={"per_page": per_page})
        response.raise_for_status()
        releases = response.json()

    source = f"github/{owner}/{repo}"
    for release in releases:
        tag = release.get("tag_name", "unknown")
        item = {
            "item_id": _item_id(source, tag),
            "source": source,
            "source_type": "github_release",
            "title": release.get("name") or tag,
            "body": release.get("body", ""),
            "url": release.get("html_url", ""),
            "tag": tag,
            "published_at": release.get("published_at", ""),
            "is_prerelease": release.get("prerelease", False),
            "fetched_at": datetime.now(UTC).isoformat(),
        }
        items.append(item)

    logger.info("Fetched %d releases from %s/%s", len(items), owner, repo)
    return items


def fetch_keps(owner: str = "kubernetes", repo: str = "enhancements") -> list[dict[str, Any]]:
    """Fetch KEP (Kubernetes Enhancement Proposal) metadata.

    Browses the keps/ directory tree and fetches kep.yaml files for metadata.
    """
    url = f"{BASE_URL}/repos/{owner}/{repo}/git/trees/master"
    items = []

    with httpx.Client(timeout=TIMEOUT, headers=_headers()) as client:
        # Get the top-level tree
        response = client.get(url, params={"recursive": "false"})
        response.raise_for_status()
        tree = response.json()

        # Find the keps directory
        keps_tree = None
        for entry in tree.get("tree", []):
            if entry["path"] == "keps" and entry["type"] == "tree":
                keps_tree = entry
                break

        if not keps_tree:
            logger.warning("Could not find keps/ directory in %s/%s", owner, repo)
            return items

        # Get the keps subtree (one level — SIG directories)
        response = client.get(keps_tree["url"], params={"recursive": "true"})
        response.raise_for_status()
        keps_entries = response.json()

        # Find README.md files in KEP directories (they contain the proposal)
        kep_readmes = [
            entry
            for entry in keps_entries.get("tree", [])
            if entry["path"].endswith("/README.md") and entry["type"] == "blob"
        ]

        # Limit to most recent KEPs to stay within rate limits
        for entry in kep_readmes[:100]:
            kep_path = entry["path"]
            kep_number = kep_path.split("/")[-2] if "/" in kep_path else kep_path

            item = {
                "item_id": _item_id("github/kubernetes/enhancements", kep_path),
                "source": "github/kubernetes/enhancements",
                "source_type": "kep",
                "title": f"KEP: {kep_number}",
                "url": f"https://github.com/{owner}/{repo}/tree/master/keps/{kep_path}",
                "kep_path": kep_path,
                "blob_sha": entry.get("sha", ""),
                "fetched_at": datetime.now(UTC).isoformat(),
            }
            items.append(item)

    logger.info("Fetched %d KEP entries from %s/%s", len(items), owner, repo)
    return items
