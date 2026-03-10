"""Tests for RSS ingestion client."""

from unittest.mock import patch

from src.ingestion.rss_client import fetch_rss

SAMPLE_FEED_DATA = {
    "bozo": False,
    "entries": [
        {
            "title": "Kubernetes v1.31: New Features and Deprecations",
            "link": "https://kubernetes.io/blog/2024/08/13/kubernetes-v1-31-release/",
            "summary": "The Kubernetes v1.31 release introduces several new features...",
            "published_parsed": (2024, 8, 13, 0, 0, 0, 1, 225, 0),
        },
        {
            "title": "Gateway API v1.1 Graduated",
            "link": "https://kubernetes.io/blog/2024/05/gateway-api-v1-1/",
            "summary": "Gateway API has graduated several features to stable...",
            "published_parsed": (2024, 5, 15, 0, 0, 0, 2, 136, 0),
        },
    ],
}


@patch("src.ingestion.rss_client.feedparser.parse")
def test_fetch_rss(mock_parse):
    mock_parse.return_value = SAMPLE_FEED_DATA

    items = fetch_rss("https://kubernetes.io/feed.xml", "kubernetes-blog")

    assert len(items) == 2
    item = items[0]
    assert item["source"] == "rss/kubernetes-blog"
    assert item["source_type"] == "rss"
    assert "v1.31" in item["title"]
    assert item["url"] == "https://kubernetes.io/blog/2024/08/13/kubernetes-v1-31-release/"
    assert item["item_id"]


@patch("src.ingestion.rss_client.feedparser.parse")
def test_fetch_rss_empty_feed(mock_parse):
    mock_parse.return_value = {"bozo": False, "entries": []}
    items = fetch_rss("https://example.com/feed.xml", "empty")
    assert items == []


@patch("src.ingestion.rss_client.feedparser.parse")
def test_fetch_rss_bozo_with_no_entries(mock_parse):
    mock_parse.return_value = {
        "bozo": True,
        "bozo_exception": Exception("malformed feed"),
        "entries": [],
    }
    items = fetch_rss("https://broken.com/feed.xml", "broken")
    assert items == []


@patch("src.ingestion.rss_client.feedparser.parse")
def test_fetch_rss_respects_max_entries(mock_parse):
    mock_parse.return_value = {
        "bozo": False,
        "entries": [
            {"title": f"Entry {i}", "link": f"https://example.com/{i}"} for i in range(100)
        ],
    }
    items = fetch_rss("https://example.com/feed.xml", "test", max_entries=5)
    assert len(items) == 5
