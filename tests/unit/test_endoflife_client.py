"""Tests for endoflife.date ingestion client."""

from unittest.mock import MagicMock, patch

from src.ingestion.endoflife_client import fetch_product_cycles

SAMPLE_CYCLES = [
    {
        "cycle": "1.31",
        "releaseDate": "2024-08-13",
        "eol": "2025-10-28",
        "latest": "1.31.4",
        "lts": False,
    },
    {
        "cycle": "1.30",
        "releaseDate": "2024-04-17",
        "eol": "2025-06-28",
        "latest": "1.30.8",
        "lts": False,
    },
    {
        "cycle": "1.28",
        "releaseDate": "2023-08-15",
        "eol": True,
        "latest": "1.28.15",
        "lts": False,
    },
]


@patch("src.ingestion.endoflife_client.httpx.Client")
def test_fetch_product_cycles(mock_client_cls):
    mock_response = MagicMock()
    mock_response.json.return_value = SAMPLE_CYCLES
    mock_response.raise_for_status = MagicMock()

    mock_client = MagicMock()
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=False)
    mock_client.get.return_value = mock_response
    mock_client_cls.return_value = mock_client

    items = fetch_product_cycles("kubernetes")

    assert len(items) == 3
    item = items[0]
    assert item["source"] == "eol/kubernetes"
    assert item["source_type"] == "endoflife"
    assert item["cycle"] == "1.31"
    assert item["latest_version"] == "1.31.4"
    assert item["item_id"]


@patch("src.ingestion.endoflife_client.httpx.Client")
def test_eol_boolean_true(mock_client_cls):
    mock_response = MagicMock()
    mock_response.json.return_value = [{"cycle": "1.28", "eol": True, "latest": "1.28.15"}]
    mock_response.raise_for_status = MagicMock()

    mock_client = MagicMock()
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=False)
    mock_client.get.return_value = mock_response
    mock_client_cls.return_value = mock_client

    items = fetch_product_cycles("kubernetes")
    assert items[0]["is_eol"] is True


@patch("src.ingestion.endoflife_client.httpx.Client")
def test_eol_date_in_future(mock_client_cls):
    mock_response = MagicMock()
    mock_response.json.return_value = [{"cycle": "1.31", "eol": "2099-12-31", "latest": "1.31.4"}]
    mock_response.raise_for_status = MagicMock()

    mock_client = MagicMock()
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=False)
    mock_client.get.return_value = mock_response
    mock_client_cls.return_value = mock_client

    items = fetch_product_cycles("kubernetes")
    assert items[0]["is_eol"] is False
    assert items[0]["eol_date"] == "2099-12-31"
