"""Start all ingestion flows as scheduled deployments using serve()."""

import sys
from pathlib import Path

# Ensure project root is on sys.path so `src` and `flows` are importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from prefect import serve  # noqa: E402

from flows.ingest_cves import ingest_k8s_cves  # noqa: E402
from flows.ingest_eol import ingest_endoflife  # noqa: E402
from flows.ingest_github import ingest_github_releases  # noqa: E402
from flows.ingest_rss import ingest_rss_feeds  # noqa: E402
from flows.process_and_embed import process_and_embed  # noqa: E402

if __name__ == "__main__":
    github_deploy = ingest_github_releases.to_deployment(
        name="ingest-github-releases",
        cron="0 6 * * *",
    )
    rss_deploy = ingest_rss_feeds.to_deployment(
        name="ingest-rss-feeds",
        cron="0 7 * * *",
    )
    cve_deploy = ingest_k8s_cves.to_deployment(
        name="ingest-k8s-cves",
        cron="0 9 * * *",
    )
    eol_deploy = ingest_endoflife.to_deployment(
        name="ingest-endoflife",
        cron="0 8 * * *",
    )

    process_deploy = process_and_embed.to_deployment(
        name="process-and-embed",
        cron="0 10 * * *",  # Run after all ingestion flows complete
    )

    serve(github_deploy, rss_deploy, cve_deploy, eol_deploy, process_deploy)
