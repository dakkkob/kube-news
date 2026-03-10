"""Tests for GitHub ingestion client."""

from unittest.mock import MagicMock, patch

from src.ingestion.github_client import fetch_releases

SAMPLE_RELEASE = {
    "tag_name": "v1.31.0",
    "name": "Kubernetes v1.31.0",
    "body": "## What's New\n\n### Deprecations\n\n- Removed `flowcontrol.apiserver.k8s.io/v1beta3`",
    "html_url": "https://github.com/kubernetes/kubernetes/releases/tag/v1.31.0",
    "published_at": "2024-08-13T00:00:00Z",
    "prerelease": False,
}


@patch("src.ingestion.github_client.httpx.Client")
def test_fetch_releases(mock_client_cls):
    mock_response = MagicMock()
    mock_response.json.return_value = [SAMPLE_RELEASE]
    mock_response.raise_for_status = MagicMock()

    mock_client = MagicMock()
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=False)
    mock_client.get.return_value = mock_response
    mock_client_cls.return_value = mock_client

    items = fetch_releases("kubernetes", "kubernetes")

    assert len(items) == 1
    item = items[0]
    assert item["source"] == "github/kubernetes/kubernetes"
    assert item["source_type"] == "github_release"
    assert item["title"] == "Kubernetes v1.31.0"
    assert item["tag"] == "v1.31.0"
    assert "Deprecations" in item["body"]
    assert item["item_id"]  # Should be a hash


@patch("src.ingestion.github_client.httpx.Client")
def test_fetch_releases_empty(mock_client_cls):
    mock_response = MagicMock()
    mock_response.json.return_value = []
    mock_response.raise_for_status = MagicMock()

    mock_client = MagicMock()
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=False)
    mock_client.get.return_value = mock_response
    mock_client_cls.return_value = mock_client

    items = fetch_releases("kubernetes", "kubernetes")
    assert items == []


def test_item_ids_are_deterministic():
    """Same input should produce the same item_id."""
    from src.ingestion.github_client import _item_id

    id1 = _item_id("github/kubernetes/kubernetes", "v1.31.0")
    id2 = _item_id("github/kubernetes/kubernetes", "v1.31.0")
    assert id1 == id2

    id3 = _item_id("github/kubernetes/kubernetes", "v1.30.0")
    assert id1 != id3
