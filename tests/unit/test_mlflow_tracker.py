"""Tests for MLflow tracking (MLflow mocked)."""

import sys
from unittest.mock import MagicMock, patch

# Insert a mock mlflow into sys.modules so the import inside _ensure_mlflow works
mock_mlflow = MagicMock()
sys.modules["mlflow"] = mock_mlflow

from src.mlops.mlflow_tracker import log_classification_batch  # noqa: E402


@patch("src.mlops.mlflow_tracker.MLFLOW_TRACKING_URI", "https://dagshub.com/test/test.mlflow")
def test_log_classification_batch() -> None:
    """Metrics are logged correctly for a classification batch."""
    mock_mlflow.reset_mock()

    items = [
        {"item_id": "a", "label": "deprecation", "confidence": 0.9, "source": "github"},
        {"item_id": "b", "label": "security", "confidence": 0.8, "source": "cve"},
        {"item_id": "c", "label": "unknown", "confidence": 0.1, "source": "rss"},
    ]

    log_classification_batch(items, batch_size=20, upserted=3)

    mock_mlflow.set_tracking_uri.assert_called_once()
    mock_mlflow.set_experiment.assert_called_once_with("kube-news-classifier")
    mock_mlflow.start_run.assert_called_once()

    # Verify metrics were logged via the context manager
    run_ctx = mock_mlflow.start_run.return_value.__enter__.return_value  # noqa: F841
    assert mock_mlflow.log_metric.call_count >= 5  # total, classified, unknown, avg_conf, upserted
    assert mock_mlflow.set_tag.call_count >= 2  # source_count, sources, pipeline


@patch("src.mlops.mlflow_tracker.MLFLOW_TRACKING_URI", "")
def test_log_skipped_when_no_uri() -> None:
    """No MLflow calls when URI is not configured."""
    mock_mlflow.reset_mock()
    items = [{"item_id": "a", "label": "deprecation", "confidence": 0.9, "source": "github"}]
    log_classification_batch(items, batch_size=20, upserted=1)
    mock_mlflow.set_tracking_uri.assert_not_called()
