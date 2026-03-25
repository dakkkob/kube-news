"""Weekly drift detection flow.

Runs after process-and-embed to check whether the classifier or embedding
distribution has shifted.  If drift exceeds thresholds, triggers a GitHub
Actions retraining workflow via repository_dispatch.
"""

import sys
from dataclasses import asdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx  # noqa: E402
from prefect import flow, task  # noqa: E402

from src.config import GITHUB_TOKEN  # noqa: E402
from src.mlops.drift_detector import DriftResult, run_all_checks  # noqa: E402

GITHUB_REPO = "dakkkob/kube-news"


@task(retries=1, retry_delay_seconds=30, log_prints=True)
def detect_drift() -> list[DriftResult]:
    """Run all drift checks."""
    results = run_all_checks()
    for r in results:
        status = "DRIFTED" if r.is_drifted else "OK"
        print(
            f"  [{r.check_type}] {status} — current={r.current_value:.4f}, "
            f"baseline={r.baseline_value:.4f}"
        )
    return results


@task(retries=1, retry_delay_seconds=30, log_prints=True)
def trigger_retraining(drift_results: list[DriftResult]) -> bool:
    """If any check shows drift, send repository_dispatch to GitHub."""
    drifted = [r for r in drift_results if r.is_drifted]
    if not drifted:
        print("No drift detected — skipping retraining trigger.")
        return False

    if not GITHUB_TOKEN:
        print("GITHUB_TOKEN not set — cannot trigger retraining.")
        return False

    print(
        f"Drift detected in {len(drifted)} check(s): "
        f"{[r.check_type for r in drifted]}. Triggering retraining."
    )

    response = httpx.post(
        f"https://api.github.com/repos/{GITHUB_REPO}/dispatches",
        headers={
            "Authorization": f"Bearer {GITHUB_TOKEN}",
            "Accept": "application/vnd.github+json",
        },
        json={
            "event_type": "drift-detected",
            "client_payload": {
                "checks": [asdict(r) for r in drifted],
            },
        },
        timeout=30,
    )
    response.raise_for_status()
    print("Retraining workflow triggered successfully.")
    return True


@flow(name="drift-check", log_prints=True)
def drift_check() -> dict[str, bool]:
    """Run drift detection and optionally trigger retraining."""
    results = detect_drift()
    triggered = trigger_retraining(results)
    return {"triggered": triggered}


if __name__ == "__main__":
    drift_check()
