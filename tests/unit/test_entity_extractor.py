"""Tests for Kubernetes entity extraction."""

from src.processing.entity_extractor import extract_entities


def test_extract_cve_ids():
    text = "Fixed CVE-2024-12345 and CVE-2023-9876 in this release."
    entities = extract_entities(text)
    assert "CVE-2024-12345" in entities["cve_ids"]
    assert "CVE-2023-9876" in entities["cve_ids"]


def test_extract_api_versions():
    text = "Migrated from v1beta1 to v1 for the Gateway API."
    entities = extract_entities(text)
    assert "v1" in entities["api_versions"]
    assert "v1beta1" in entities["api_versions"]


def test_extract_k8s_kinds():
    text = "The Deployment and Service resources now support Gateway API with HTTPRoute."
    entities = extract_entities(text)
    assert "Deployment" in entities["k8s_kinds"]
    assert "Service" in entities["k8s_kinds"]
    assert "HTTPRoute" in entities["k8s_kinds"]


def test_extract_versions():
    text = "Kubernetes v1.31.0 and Helm 3.15.2 released."
    entities = extract_entities(text)
    assert "1.31.0" in entities["versions"]
    assert "3.15.2" in entities["versions"]


def test_extract_empty_text():
    entities = extract_entities("")
    assert entities["cve_ids"] == []
    assert entities["api_versions"] == []
    assert entities["k8s_kinds"] == []
    assert entities["versions"] == []


def test_extract_no_duplicates():
    text = "Pod Pod Pod Deployment Deployment"
    entities = extract_entities(text)
    assert entities["k8s_kinds"].count("Pod") == 1
    assert entities["k8s_kinds"].count("Deployment") == 1
