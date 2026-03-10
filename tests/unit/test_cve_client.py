"""Tests for CVE ingestion client."""

from unittest.mock import MagicMock, patch

from src.ingestion.cve_client import fetch_k8s_cves

SAMPLE_CVE_FEED = {
    "items": [
        {
            "id": "CVE-2024-12345",
            "title": "Kubernetes API Server Vulnerability",
            "content_text": "A vulnerability was found in the Kubernetes API server...",
            "external_url": "https://github.com/kubernetes/kubernetes/issues/12345",
            "date_published": "2024-07-15T00:00:00Z",
        },
        {
            "id": "CVE-2024-67890",
            "title": "kubelet Privilege Escalation",
            "content_text": "A privilege escalation vulnerability in kubelet...",
            "external_url": "https://github.com/kubernetes/kubernetes/issues/67890",
            "date_published": "2024-06-20T00:00:00Z",
        },
    ]
}


@patch("src.ingestion.cve_client.httpx.Client")
def test_fetch_k8s_cves(mock_client_cls):
    mock_response = MagicMock()
    mock_response.json.return_value = SAMPLE_CVE_FEED
    mock_response.raise_for_status = MagicMock()

    mock_client = MagicMock()
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=False)
    mock_client.get.return_value = mock_response
    mock_client_cls.return_value = mock_client

    items = fetch_k8s_cves()

    assert len(items) == 2
    item = items[0]
    assert item["source"] == "cve/kubernetes"
    assert item["source_type"] == "cve"
    assert item["cve_id"] == "CVE-2024-12345"
    assert "API Server" in item["title"]
    assert item["item_id"]


@patch("src.ingestion.cve_client.httpx.Client")
def test_fetch_cves_empty(mock_client_cls):
    mock_response = MagicMock()
    mock_response.json.return_value = {"items": []}
    mock_response.raise_for_status = MagicMock()

    mock_client = MagicMock()
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=False)
    mock_client.get.return_value = mock_response
    mock_client_cls.return_value = mock_client

    items = fetch_k8s_cves()
    assert items == []
