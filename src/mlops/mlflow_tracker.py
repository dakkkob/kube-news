"""MLflow tracking for classification and processing batches."""

from __future__ import annotations

import logging
from typing import Any

from src.config import MLFLOW_TRACKING_URI

logger = logging.getLogger(__name__)

EXPERIMENT_NAME = "kube-news-classifier"


def _ensure_mlflow() -> bool:
    """Check if MLflow is configured and available."""
    if not MLFLOW_TRACKING_URI:
        logger.warning("MLFLOW_TRACKING_URI not set, skipping MLflow tracking")
        return False

    try:
        import mlflow  # noqa: F401

        return True
    except ImportError:
        logger.warning("mlflow not installed, skipping tracking")
        return False


def log_classification_batch(
    items: list[dict[str, Any]],
    batch_size: int,
    upserted: int,
) -> None:
    """Log classification batch metrics to MLflow.

    Tracks: label distribution, avg confidence, item counts, sources.
    """
    if not _ensure_mlflow():
        return

    import mlflow

    mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)
    mlflow.set_experiment(EXPERIMENT_NAME)

    # Compute metrics
    labels = [item.get("label", "unknown") for item in items]
    confidences = [float(item.get("confidence", 0.0)) for item in items]

    label_counts: dict[str, int] = {}
    for label in labels:
        label_counts[label] = label_counts.get(label, 0) + 1

    sources: set[str] = set()
    for item in items:
        sources.add(item.get("source", "unknown"))

    avg_confidence = sum(confidences) / len(confidences) if confidences else 0.0
    classified_count = sum(1 for lbl in labels if lbl not in ("unknown", ""))

    with mlflow.start_run():
        # Batch-level metrics
        mlflow.log_metric("total_items", len(items))
        mlflow.log_metric("classified_items", classified_count)
        mlflow.log_metric("unknown_items", len(items) - classified_count)
        mlflow.log_metric("avg_confidence", round(avg_confidence, 4))
        mlflow.log_metric("upserted_to_qdrant", upserted)
        mlflow.log_metric("batch_size", batch_size)

        # Per-label counts
        for label, count in label_counts.items():
            mlflow.log_metric(f"label_{label}", count)

        # Tags
        mlflow.set_tag("source_count", str(len(sources)))
        mlflow.set_tag("sources", ", ".join(sorted(sources)))
        mlflow.set_tag("pipeline", "process-and-embed")

    logger.info("Logged MLflow run: %d items, %.2f avg confidence", len(items), avg_confidence)
