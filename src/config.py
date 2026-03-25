"""Load and validate source configuration from sources.yaml."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel


class GitHubRepo(BaseModel):
    owner: str
    repo: str
    schedule: str = "daily"
    content_type: str = "releases"
    description: str = ""

    @property
    def full_name(self) -> str:
        return f"{self.owner}/{self.repo}"


class RSSFeed(BaseModel):
    url: str
    name: str
    schedule: str = "daily"
    description: str = ""


class CVEFeed(BaseModel):
    url: str
    name: str
    schedule: str = "every_6h"
    description: str = ""


class EndOfLifeProduct(BaseModel):
    product: str
    schedule: str = "daily"


class ArtifactHubConfig(BaseModel):
    search_url: str
    params: dict[str, Any] = {}
    schedule: str = "daily"
    description: str = ""


class SourcesConfig(BaseModel):
    github_repos: list[GitHubRepo] = []
    rss_feeds: list[RSSFeed] = []
    cve_feeds: list[CVEFeed] = []
    endoflife_products: list[EndOfLifeProduct] = []
    artifact_hub: ArtifactHubConfig | None = None


def load_sources_config(config_path: str | Path | None = None) -> SourcesConfig:
    if config_path is None:
        config_path = Path(__file__).parent.parent / "config" / "sources.yaml"
    config_path = Path(config_path)

    with open(config_path) as f:
        raw = yaml.safe_load(f)

    return SourcesConfig(**raw)


# Common settings
S3_BUCKET = os.environ.get("S3_BUCKET", "kube-news-raw")
DYNAMODB_TABLE = os.environ.get("DYNAMODB_TABLE", "kube-news")
AWS_REGION = os.environ.get("AWS_REGION", "eu-north-1")
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
HF_API_TOKEN = os.environ.get("HF_API_TOKEN", "")
QDRANT_URL = os.environ.get("QDRANT_URL", "")
QDRANT_API_KEY = os.environ.get("QDRANT_API_KEY", "")
QDRANT_COLLECTION = os.environ.get("QDRANT_COLLECTION", "kube-news")
MLFLOW_TRACKING_URI = os.environ.get("MLFLOW_TRACKING_URI", "")
MLFLOW_TRACKING_USERNAME = os.environ.get("MLFLOW_TRACKING_USERNAME", "")
MLFLOW_TRACKING_PASSWORD = os.environ.get("MLFLOW_TRACKING_PASSWORD", "")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")

# Phase 4: MLOps
CLASSIFIER_MODEL_PATH = os.environ.get("CLASSIFIER_MODEL_PATH", "")
DRIFT_METRICS_TABLE = os.environ.get("DRIFT_METRICS_TABLE", "kube-news-drift-metrics")
CLASSIFIER_S3_PREFIX = os.environ.get("CLASSIFIER_S3_PREFIX", "models/classifier/")
