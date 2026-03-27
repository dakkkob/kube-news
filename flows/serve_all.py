"""Start all flows as scheduled deployments using serve().

Prefect Cloud free tier allows 5 deployments max, so ingestion is
consolidated into a single 'ingest-all' flow.
"""

import sys
from pathlib import Path

# Ensure project root is on sys.path so `src` and `flows` are importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from prefect import serve  # noqa: E402

from flows.drift_check import drift_check  # noqa: E402
from flows.ingest_all import ingest_all  # noqa: E402
from flows.process_and_embed import process_and_embed  # noqa: E402

if __name__ == "__main__":
    # Mon/Wed/Fri schedule. EC2 starts at 05:50, stops at 08:00 UTC.
    ingest_deploy = ingest_all.to_deployment(
        name="ingest-all",
        cron="0 6 * * 1,3,5",
    )
    process_deploy = process_and_embed.to_deployment(
        name="process-and-embed",
        cron="15 7 * * 1,3,5",  # After ingestion completes (~45 min)
    )
    drift_deploy = drift_check.to_deployment(
        name="drift-check",
        cron="45 7 * * 1,3,5",  # After process-and-embed finishes (~7:30)
    )

    serve(ingest_deploy, process_deploy, drift_deploy)
