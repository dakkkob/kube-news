"""Drift detection for the kube-news classifier.

Two signals:
1. Confidence drift — 7-day avg confidence vs stored baseline.
2. Embedding drift — PSI on PCA-reduced document vectors vs baseline.
"""

from __future__ import annotations

import io
import json
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import numpy as np

from src.config import AWS_REGION, S3_BUCKET
from src.storage.dynamodb_client import (
    get_drift_baseline,
    query_classified_items,
    save_drift_baseline,
    save_drift_metric,
)

logger = logging.getLogger(__name__)

CONFIDENCE_THRESHOLD = 0.05
PSI_THRESHOLD = 0.2
PSI_BINS = 10
PCA_COMPONENTS = 10
DRIFT_BASELINE_S3_KEY = "models/drift/pca_baseline.npz"


@dataclass
class DriftResult:
    check_type: str
    current_value: float
    baseline_value: float
    threshold: float
    is_drifted: bool
    timestamp: str
    details: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# PSI helpers
# ---------------------------------------------------------------------------


def _compute_psi(expected: np.ndarray, actual: np.ndarray, bins: int = PSI_BINS) -> float:
    """Compute Population Stability Index between two 1-D distributions."""
    # Use bin edges from the expected distribution
    _, bin_edges = np.histogram(expected, bins=bins)
    expected_counts = np.histogram(expected, bins=bin_edges)[0].astype(float)
    actual_counts = np.histogram(actual, bins=bin_edges)[0].astype(float)

    # Smooth zeros to avoid log(0)
    expected_pct = (expected_counts + 1) / (expected_counts.sum() + bins)
    actual_pct = (actual_counts + 1) / (actual_counts.sum() + bins)

    psi: float = float(np.sum((actual_pct - expected_pct) * np.log(actual_pct / expected_pct)))
    return psi


def _fit_pca(vectors: np.ndarray, n_components: int = PCA_COMPONENTS) -> dict[str, np.ndarray]:
    """Fit PCA on vectors and return components + mean for later projection."""
    mean = vectors.mean(axis=0)
    centered = vectors - mean
    # SVD-based PCA (avoid sklearn dependency for this lightweight operation)
    _, _, vt = np.linalg.svd(centered, full_matrices=False)
    components = vt[:n_components]
    return {"mean": mean, "components": components}


def _project_pca(vectors: np.ndarray, pca: dict[str, np.ndarray]) -> np.ndarray:
    """Project vectors using stored PCA parameters."""
    centered = vectors - pca["mean"]
    projected: np.ndarray = centered @ pca["components"].T
    return projected


# ---------------------------------------------------------------------------
# S3 helpers for PCA baseline
# ---------------------------------------------------------------------------


def _save_pca_baseline_to_s3(pca: dict[str, np.ndarray], projected: np.ndarray) -> None:
    """Save PCA parameters and baseline projected vectors to S3."""
    import boto3

    buf = io.BytesIO()
    np.savez_compressed(
        buf,
        pca_mean=pca["mean"],
        pca_components=pca["components"],
        baseline_projected=projected,
    )
    buf.seek(0)

    s3 = boto3.client("s3", region_name=AWS_REGION)
    s3.put_object(Bucket=S3_BUCKET, Key=DRIFT_BASELINE_S3_KEY, Body=buf.getvalue())
    logger.info("Saved PCA baseline to s3://%s/%s", S3_BUCKET, DRIFT_BASELINE_S3_KEY)


def _load_pca_baseline_from_s3() -> dict[str, np.ndarray] | None:
    """Load PCA baseline from S3. Returns None if not found."""
    import boto3
    from botocore.exceptions import ClientError

    s3 = boto3.client("s3", region_name=AWS_REGION)
    try:
        response = s3.get_object(Bucket=S3_BUCKET, Key=DRIFT_BASELINE_S3_KEY)
        data = np.load(io.BytesIO(response["Body"].read()))
        return {
            "pca_mean": data["pca_mean"],
            "pca_components": data["pca_components"],
            "baseline_projected": data["baseline_projected"],
        }
    except ClientError as e:
        if e.response["Error"]["Code"] == "NoSuchKey":
            logger.warning("No PCA baseline found in S3")
            return None
        raise


# ---------------------------------------------------------------------------
# Drift checks
# ---------------------------------------------------------------------------


def check_confidence_drift(days: int = 7) -> DriftResult:
    """Compare recent average confidence to the stored baseline."""
    now = datetime.now(UTC).isoformat()

    items = query_classified_items(days=days, min_confidence=0.0, limit=1000)
    if not items:
        return DriftResult(
            check_type="confidence",
            current_value=0.0,
            baseline_value=0.0,
            threshold=CONFIDENCE_THRESHOLD,
            is_drifted=False,
            timestamp=now,
            details={"error": "no_recent_items"},
        )

    confidences = [float(item.get("confidence", "0") or "0") for item in items]
    current_avg = float(np.mean(confidences))

    baseline = get_drift_baseline("confidence")
    if baseline is None:
        # No baseline yet — save current as baseline, no drift
        save_drift_baseline(
            "confidence",
            {
                "mean_confidence": str(current_avg),
                "sample_count": str(len(items)),
            },
        )
        return DriftResult(
            check_type="confidence",
            current_value=current_avg,
            baseline_value=current_avg,
            threshold=CONFIDENCE_THRESHOLD,
            is_drifted=False,
            timestamp=now,
            details={"action": "baseline_created", "sample_count": len(items)},
        )

    baseline_avg = float(baseline.get("mean_confidence", "0"))
    delta = baseline_avg - current_avg
    is_drifted = delta > CONFIDENCE_THRESHOLD

    result = DriftResult(
        check_type="confidence",
        current_value=round(current_avg, 4),
        baseline_value=round(baseline_avg, 4),
        threshold=CONFIDENCE_THRESHOLD,
        is_drifted=is_drifted,
        timestamp=now,
        details={
            "delta": round(delta, 4),
            "sample_count": len(items),
        },
    )

    # Persist to drift-metrics table
    save_drift_metric(
        "confidence",
        now,
        {
            "current_value": str(round(current_avg, 4)),
            "baseline_value": str(round(baseline_avg, 4)),
            "delta": str(round(delta, 4)),
            "is_drifted": str(is_drifted).lower(),
            "sample_count": str(len(items)),
        },
    )

    return result


def check_embedding_drift(days: int = 7) -> DriftResult:
    """Compare recent embedding distribution to baseline using PSI."""
    now = datetime.now(UTC).isoformat()

    # Fetch recent vectors from Qdrant
    from src.storage.qdrant_client import scroll_vectors

    recent_vectors = scroll_vectors(limit=500)
    if len(recent_vectors) < 20:
        return DriftResult(
            check_type="embedding_psi",
            current_value=0.0,
            baseline_value=0.0,
            threshold=PSI_THRESHOLD,
            is_drifted=False,
            timestamp=now,
            details={"error": "insufficient_vectors", "count": len(recent_vectors)},
        )

    recent_arr = np.array(recent_vectors)

    baseline_data = _load_pca_baseline_from_s3()
    if baseline_data is None:
        # First run — create baseline
        pca = _fit_pca(recent_arr)
        projected = _project_pca(recent_arr, pca)
        _save_pca_baseline_to_s3(pca, projected)
        save_drift_baseline(
            "embedding_psi",
            {
                "vector_count": str(len(recent_vectors)),
            },
        )
        return DriftResult(
            check_type="embedding_psi",
            current_value=0.0,
            baseline_value=0.0,
            threshold=PSI_THRESHOLD,
            is_drifted=False,
            timestamp=now,
            details={"action": "baseline_created", "vector_count": len(recent_vectors)},
        )

    # Project current vectors using stored PCA
    pca = {
        "mean": baseline_data["pca_mean"],
        "components": baseline_data["pca_components"],
    }
    baseline_projected = baseline_data["baseline_projected"]
    current_projected = _project_pca(recent_arr, pca)

    # Compute PSI per PCA component and average
    psi_per_component = []
    n_components = min(baseline_projected.shape[1], current_projected.shape[1])
    for i in range(n_components):
        psi = _compute_psi(baseline_projected[:, i], current_projected[:, i])
        psi_per_component.append(psi)

    avg_psi = float(np.mean(psi_per_component))
    is_drifted = avg_psi > PSI_THRESHOLD

    result = DriftResult(
        check_type="embedding_psi",
        current_value=round(avg_psi, 4),
        baseline_value=0.0,
        threshold=PSI_THRESHOLD,
        is_drifted=is_drifted,
        timestamp=now,
        details={
            "psi_per_component": [round(p, 4) for p in psi_per_component],
            "vector_count": len(recent_vectors),
        },
    )

    save_drift_metric(
        "embedding_psi",
        now,
        {
            "current_value": str(round(avg_psi, 4)),
            "threshold": str(PSI_THRESHOLD),
            "is_drifted": str(is_drifted).lower(),
            "vector_count": str(len(recent_vectors)),
            "psi_per_component": json.dumps([round(p, 4) for p in psi_per_component]),
        },
    )

    return result


def run_all_checks(days: int = 7) -> list[DriftResult]:
    """Run all drift checks and return results."""
    results: list[DriftResult] = []

    try:
        results.append(check_confidence_drift(days=days))
    except Exception:
        logger.exception("Confidence drift check failed")

    try:
        results.append(check_embedding_drift(days=days))
    except Exception:
        logger.exception("Embedding drift check failed")

    for r in results:
        status = "DRIFT DETECTED" if r.is_drifted else "OK"
        logger.info(
            "Drift check [%s]: %s (current=%.4f, baseline=%.4f, threshold=%.4f)",
            r.check_type,
            status,
            r.current_value,
            r.baseline_value,
            r.threshold,
        )

    return results
