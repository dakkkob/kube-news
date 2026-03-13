"""Tests for zero-shot classifier (HuggingFace API mocked)."""

from unittest.mock import MagicMock, patch

from src.processing.classifier import classify_batch, classify_text


@patch("src.processing.classifier.HF_API_TOKEN", "fake-token")
@patch("src.processing.classifier.httpx.post")
def test_classify_text_deprecation(mock_post):
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "labels": ["deprecation", "feature", "release", "security", "blog", "end of life"],
        "scores": [0.85, 0.05, 0.04, 0.03, 0.02, 0.01],
    }
    mock_response.raise_for_status = MagicMock()
    mock_post.return_value = mock_response

    result = classify_text("PodSecurityPolicy is deprecated in Kubernetes 1.25")
    assert result["label"] == "deprecation"
    assert result["confidence"] == 0.85
    assert "deprecation" in result["all_scores"]


@patch("src.processing.classifier.HF_API_TOKEN", "fake-token")
@patch("src.processing.classifier.httpx.post")
def test_classify_text_below_threshold(mock_post):
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "labels": ["blog", "feature"],
        "scores": [0.2, 0.15],
    }
    mock_response.raise_for_status = MagicMock()
    mock_post.return_value = mock_response

    result = classify_text("Some ambiguous text", threshold=0.3)
    assert result["label"] == "unknown"


@patch("src.processing.classifier.HF_API_TOKEN", "fake-token")
@patch("src.processing.classifier.httpx.post")
def test_classify_text_eol_mapping(mock_post):
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "labels": ["end of life", "deprecation"],
        "scores": [0.9, 0.05],
    }
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
    mock_response.json.return_value = {
        "labels": ["security", "feature"],
        "scores": [0.9, 0.05],
    }
    mock_response.raise_for_status = MagicMock()
    mock_post.return_value = mock_response

    results = classify_batch(["CVE-2024-1234 found", "New feature added"])
    assert len(results) == 2
    assert all(r["label"] for r in results)
