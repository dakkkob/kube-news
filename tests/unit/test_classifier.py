"""Tests for classifier (dual-mode: local model + zero-shot fallback)."""

from unittest.mock import MagicMock, patch

from src.processing.classifier import classify_batch, classify_text

# All zero-shot tests disable the local model so they hit the HF API path.
_NO_LOCAL = patch("src.processing.classifier._has_local_model", return_value=False)


@_NO_LOCAL
@patch("src.processing.classifier.HF_API_TOKEN", "fake-token")
@patch("src.processing.classifier.httpx.post")
def test_classify_text_deprecation_new_format(mock_post, _mock_local):
    """Test with new HF API format: list of {label, score} dicts."""
    mock_response = MagicMock()
    mock_response.json.return_value = [
        {"label": "deprecation", "score": 0.85},
        {"label": "feature", "score": 0.05},
        {"label": "release", "score": 0.04},
        {"label": "security", "score": 0.03},
        {"label": "blog", "score": 0.02},
        {"label": "end of life", "score": 0.01},
    ]
    mock_response.raise_for_status = MagicMock()
    mock_post.return_value = mock_response

    result = classify_text("PodSecurityPolicy is deprecated in Kubernetes 1.25")
    assert result["label"] == "deprecation"
    assert result["confidence"] == 0.85
    assert "deprecation" in result["all_scores"]


@_NO_LOCAL
@patch("src.processing.classifier.HF_API_TOKEN", "fake-token")
@patch("src.processing.classifier.httpx.post")
def test_classify_text_old_format(mock_post, _mock_local):
    """Test with old HF API format: {labels: [...], scores: [...]}."""
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "labels": ["deprecation", "feature"],
        "scores": [0.85, 0.05],
    }
    mock_response.raise_for_status = MagicMock()
    mock_post.return_value = mock_response

    result = classify_text("PodSecurityPolicy is deprecated in Kubernetes 1.25")
    assert result["label"] == "deprecation"
    assert result["confidence"] == 0.85


@_NO_LOCAL
@patch("src.processing.classifier.HF_API_TOKEN", "fake-token")
@patch("src.processing.classifier.httpx.post")
def test_classify_text_below_threshold(mock_post, _mock_local):
    mock_response = MagicMock()
    mock_response.json.return_value = [
        {"label": "blog", "score": 0.2},
        {"label": "feature", "score": 0.15},
    ]
    mock_response.raise_for_status = MagicMock()
    mock_post.return_value = mock_response

    result = classify_text("Some ambiguous text", threshold=0.3)
    assert result["label"] == "unknown"


@_NO_LOCAL
@patch("src.processing.classifier.HF_API_TOKEN", "fake-token")
@patch("src.processing.classifier.httpx.post")
def test_classify_text_eol_mapping(mock_post, _mock_local):
    mock_response = MagicMock()
    mock_response.json.return_value = [
        {"label": "end of life", "score": 0.9},
        {"label": "deprecation", "score": 0.05},
    ]
    mock_response.raise_for_status = MagicMock()
    mock_post.return_value = mock_response

    result = classify_text("Kubernetes 1.28 reaches end of life")
    assert result["label"] == "eol"


def test_classify_text_empty():
    result = classify_text("")
    assert result["label"] == "unknown"
    assert result["confidence"] == 0.0


@_NO_LOCAL
@patch("src.processing.classifier.HF_API_TOKEN", "")
def test_classify_text_no_token(_mock_local):
    result = classify_text("Some text")
    assert result["label"] == "unknown"


@_NO_LOCAL
@patch("src.processing.classifier.HF_API_TOKEN", "fake-token")
@patch("src.processing.classifier.httpx.post")
def test_classify_batch(mock_post, _mock_local):
    mock_response = MagicMock()
    mock_response.json.return_value = [
        {"label": "security", "score": 0.9},
        {"label": "feature", "score": 0.05},
    ]
    mock_response.raise_for_status = MagicMock()
    mock_post.return_value = mock_response

    results = classify_batch(["CVE-2024-1234 found", "New feature added"])
    assert len(results) == 2
    assert all(r["label"] for r in results)


# ---------------------------------------------------------------------------
# Dual-mode tests
# ---------------------------------------------------------------------------


@patch("src.processing.classifier._has_local_model", return_value=True)
@patch("src.processing.classifier._classify_local")
def test_classify_uses_local_model_when_available(mock_local, _mock_has):
    """When local model is loaded, classify_text should use it."""
    mock_local.return_value = {"label": "security", "confidence": 0.95, "all_scores": {}}
    result = classify_text("CVE-2024-9999 critical vulnerability")
    mock_local.assert_called_once()
    assert result["label"] == "security"


@_NO_LOCAL
@patch("src.processing.classifier.HF_API_TOKEN", "fake-token")
@patch("src.processing.classifier.httpx.post")
def test_classify_falls_back_to_zero_shot(mock_post, _mock_local):
    """When no local model, classify_text should use zero-shot API."""
    mock_response = MagicMock()
    mock_response.json.return_value = [
        {"label": "feature", "score": 0.8},
        {"label": "release", "score": 0.1},
    ]
    mock_response.raise_for_status = MagicMock()
    mock_post.return_value = mock_response

    result = classify_text("New Gateway API support")
    mock_post.assert_called_once()
    assert result["label"] == "feature"
