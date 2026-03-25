"""Tests for drift detection (PSI computation and confidence drift)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import numpy as np

from src.mlops.drift_detector import (
    _compute_psi,
    _fit_pca,
    _project_pca,
    check_confidence_drift,
)

# ---------------------------------------------------------------------------
# PSI unit tests
# ---------------------------------------------------------------------------


def test_psi_identical_distributions() -> None:
    """PSI should be ~0 for identical distributions."""
    rng = np.random.default_rng(42)
    data = rng.normal(0, 1, size=1000)
    psi = _compute_psi(data, data)
    assert psi < 0.01


def test_psi_shifted_distribution() -> None:
    """PSI should be significant for a clearly shifted distribution."""
    rng = np.random.default_rng(42)
    expected = rng.normal(0, 1, size=1000)
    actual = rng.normal(2, 1, size=1000)  # Mean-shifted by 2 std devs
    psi = _compute_psi(expected, actual)
    assert psi > 0.2  # Should exceed "moderate shift" threshold


def test_psi_slightly_shifted() -> None:
    """PSI should be moderate for a slight shift."""
    rng = np.random.default_rng(42)
    expected = rng.normal(0, 1, size=1000)
    actual = rng.normal(0.3, 1, size=1000)  # Slight shift
    psi = _compute_psi(expected, actual)
    assert 0.0 < psi < 0.5  # Detectable but not extreme


def test_psi_non_negative() -> None:
    """PSI should always be non-negative."""
    rng = np.random.default_rng(42)
    for _ in range(10):
        expected = rng.normal(0, 1, size=200)
        actual = rng.normal(rng.uniform(-1, 1), 1, size=200)
        psi = _compute_psi(expected, actual)
        assert psi >= 0


# ---------------------------------------------------------------------------
# PCA unit tests
# ---------------------------------------------------------------------------


def test_pca_fit_and_project() -> None:
    """PCA should reduce dimensions and preserve relative structure."""
    rng = np.random.default_rng(42)
    vectors = rng.normal(0, 1, size=(100, 384))
    pca = _fit_pca(vectors, n_components=10)

    assert pca["mean"].shape == (384,)
    assert pca["components"].shape == (10, 384)

    projected = _project_pca(vectors, pca)
    assert projected.shape == (100, 10)


def test_pca_projection_consistency() -> None:
    """Same vectors should project to same coordinates."""
    rng = np.random.default_rng(42)
    vectors = rng.normal(0, 1, size=(50, 384))
    pca = _fit_pca(vectors, n_components=5)

    p1 = _project_pca(vectors, pca)
    p2 = _project_pca(vectors, pca)
    np.testing.assert_array_almost_equal(p1, p2)


# ---------------------------------------------------------------------------
# Confidence drift check (mocked DynamoDB)
# ---------------------------------------------------------------------------


@patch("src.mlops.drift_detector.save_drift_metric")
@patch("src.mlops.drift_detector.get_drift_baseline")
@patch("src.mlops.drift_detector.query_classified_items")
def test_confidence_drift_no_drift(
    mock_query: MagicMock,
    mock_baseline: MagicMock,
    mock_save: MagicMock,
) -> None:
    """No drift when current avg is close to baseline."""
    mock_query.return_value = [
        {"confidence": "0.85", "label": "deprecation"},
        {"confidence": "0.90", "label": "security"},
        {"confidence": "0.88", "label": "feature"},
    ]
    mock_baseline.return_value = {"mean_confidence": "0.88"}

    result = check_confidence_drift(days=7)
    assert not result.is_drifted
    assert result.check_type == "confidence"


@patch("src.mlops.drift_detector.save_drift_metric")
@patch("src.mlops.drift_detector.get_drift_baseline")
@patch("src.mlops.drift_detector.query_classified_items")
def test_confidence_drift_detected(
    mock_query: MagicMock,
    mock_baseline: MagicMock,
    mock_save: MagicMock,
) -> None:
    """Drift detected when confidence drops significantly."""
    mock_query.return_value = [
        {"confidence": "0.60", "label": "deprecation"},
        {"confidence": "0.55", "label": "unknown"},
        {"confidence": "0.58", "label": "feature"},
    ]
    mock_baseline.return_value = {"mean_confidence": "0.88"}

    result = check_confidence_drift(days=7)
    assert result.is_drifted
    assert result.details["delta"] > 0.05


@patch("src.mlops.drift_detector.save_drift_baseline")
@patch("src.mlops.drift_detector.get_drift_baseline")
@patch("src.mlops.drift_detector.query_classified_items")
def test_confidence_drift_creates_baseline(
    mock_query: MagicMock,
    mock_baseline: MagicMock,
    mock_save_baseline: MagicMock,
) -> None:
    """First run creates a baseline instead of flagging drift."""
    mock_query.return_value = [
        {"confidence": "0.85", "label": "deprecation"},
        {"confidence": "0.90", "label": "security"},
    ]
    mock_baseline.return_value = None  # No existing baseline

    result = check_confidence_drift(days=7)
    assert not result.is_drifted
    assert result.details.get("action") == "baseline_created"
    mock_save_baseline.assert_called_once()


@patch("src.mlops.drift_detector.query_classified_items")
def test_confidence_drift_no_items(mock_query: MagicMock) -> None:
    """Graceful handling when no recent items exist."""
    mock_query.return_value = []
    result = check_confidence_drift(days=7)
    assert not result.is_drifted
    assert result.details.get("error") == "no_recent_items"
