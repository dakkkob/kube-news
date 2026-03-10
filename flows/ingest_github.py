"""Prefect flow: Ingest releases from all configured GitHub repositories."""

from __future__ import annotations

import logging

from prefect import flow, task

from src.config import load_sources_config
from src.ingestion.github_client import fetch_keps, fetch_releases
from src.storage.dynamodb_client import item_exists, save_metadata
from src.storage.s3_client import save_item

logger = logging.getLogger(__name__)


@task(retries=2, retry_delay_seconds=60, log_prints=True)
def ingest_repo(owner: str, repo: str, content_type: str = "releases") -> int:
    """Fetch and store releases for a single GitHub repo. Returns count of new items."""
    items = fetch_keps(owner, repo) if content_type == "keps" else fetch_releases(owner, repo)

    new_count = 0
    for item in items:
        if item_exists(item["item_id"]):
            continue

        s3_key = save_item(item)
        save_metadata(item, s3_key=s3_key)
        new_count += 1

    print(f"{owner}/{repo}: {new_count} new items (of {len(items)} fetched)")
    return new_count


@flow(name="ingest-github-releases", log_prints=True)
def ingest_github_releases() -> dict[str, int]:
    """Ingest releases from all configured GitHub repos."""
    config = load_sources_config()
    results: dict[str, int] = {}

    for repo_config in config.github_repos:
        repo_name = repo_config.full_name
        new_count = ingest_repo(
            owner=repo_config.owner,
            repo=repo_config.repo,
            content_type=repo_config.content_type,
        )
        results[repo_name] = new_count

    total_new = sum(results.values())
    print(f"GitHub ingestion complete: {total_new} new items across {len(results)} repos")
    return results


if __name__ == "__main__":
    ingest_github_releases()
