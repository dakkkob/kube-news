"""Prefect flow: Run all ingestion flows sequentially.

Consolidates the 4 ingestion flows into a single deployment to stay within
Prefect Cloud free-tier limits (5 deployments max).
"""

from __future__ import annotations

import logging

from prefect import flow

from flows.ingest_cves import ingest_k8s_cves
from flows.ingest_eol import ingest_endoflife
from flows.ingest_github import ingest_github_releases
from flows.ingest_rss import ingest_rss_feeds

logger = logging.getLogger(__name__)


@flow(name="ingest-all", log_prints=True)
def ingest_all() -> dict:
    """Run all ingestion sources sequentially."""
    results = {}

    logger.info("Starting GitHub releases ingestion...")
    results["github"] = ingest_github_releases()

    logger.info("Starting RSS feeds ingestion...")
    results["rss"] = ingest_rss_feeds()

    logger.info("Starting CVE feed ingestion...")
    results["cves"] = ingest_k8s_cves()

    logger.info("Starting end-of-life ingestion...")
    results["eol"] = ingest_endoflife()

    logger.info("All ingestion complete: %s", results)
    return results
