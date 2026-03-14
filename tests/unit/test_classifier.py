"""Tests for zero-shot classifier (HuggingFace API mocked)."""

from unittest.mock import MagicMock, patch

from src.processing.classifier import classify_batch, classify_text


@patch("src.processing.classifier.HF_API_TOKEN", "fake-token")
@patch("src.processing.classifier.httpx.post")
def test_classify_text_deprecation_new_format(mock_post):
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


@patch("src.processing.classifier.HF_API_TOKEN", "fake-token")
@patch("src.processing.classifier.httpx.post")
def test_classify_text_old_format(mock_post):
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


@patch("src.processing.classifier.HF_API_TOKEN", "fake-token")
@patch("src.processing.classifier.httpx.post")
def test_classify_text_below_threshold(mock_post):
    mock_response = MagicMock()
    mock_response.json.return_value = [
        {"label": "blog", "score": 0.2},
        {"label": "feature", "score": 0.15},
    ]
    mock_response.raise_for_status = MagicMock()
    mock_post.return_value = mock_response

    result = classify_text("Some ambiguous text", threshold=0.3)
    assert result["label"] == "unknown"


@patch("src.processing.classifier.HF_API_TOKEN", "fake-token")
@patch("src.processing.classifier.httpx.post")
def test_classify_text_eol_mapping(mock_post):
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


@patch("src.processing.classifier.HF_API_TOKEN", "")
def test_classify_text_no_token():
    result = classify_text("Some text")
    assert result["label"] == "unknown"


@patch("src.processing.classifier.HF_API_TOKEN", "fake-token")
@patch("src.processing.classifier.httpx.post")
def test_classify_batch(mock_post):
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
