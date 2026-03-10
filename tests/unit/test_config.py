"""Tests for config loading."""

from pathlib import Path

from src.config import load_sources_config


def test_load_sources_config():
    config = load_sources_config()

    assert len(config.github_repos) > 0
    assert len(config.rss_feeds) > 0
    assert len(config.cve_feeds) > 0
    assert len(config.endoflife_products) > 0


def test_github_repos_have_required_fields():
    config = load_sources_config()

    for repo in config.github_repos:
        assert repo.owner, f"Missing owner for {repo}"
        assert repo.repo, f"Missing repo for {repo}"
        assert repo.full_name == f"{repo.owner}/{repo.repo}"


def test_kyverno_in_sources():
    """Kyverno must be tracked — CEL migration is critical."""
    config = load_sources_config()
    repos = [r.full_name for r in config.github_repos]
    assert "kyverno/kyverno" in repos


def test_kubernetes_core_in_sources():
    config = load_sources_config()
    repos = [r.full_name for r in config.github_repos]
    assert "kubernetes/kubernetes" in repos
    assert "kubernetes/enhancements" in repos


def test_rss_feeds_have_urls():
    config = load_sources_config()
    for feed in config.rss_feeds:
        assert feed.url.startswith("http"), f"Invalid URL for {feed.name}: {feed.url}"
        assert feed.name, f"Missing name for feed {feed.url}"


def test_config_path_override():
    """Config loading should accept a custom path."""
    default_path = Path(__file__).parent.parent.parent / "config" / "sources.yaml"
    config = load_sources_config(default_path)
    assert len(config.github_repos) > 0
