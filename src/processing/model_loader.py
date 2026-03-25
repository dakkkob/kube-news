"""Download and cache the fine-tuned classifier model from S3."""

from __future__ import annotations

import logging
import os
from pathlib import Path

from src.config import AWS_REGION, CLASSIFIER_MODEL_PATH, S3_BUCKET

logger = logging.getLogger(__name__)

LOCAL_CACHE_DIR = "/tmp/kube-news-model"
CURRENT_MODEL_FILE = (
    Path(__file__).resolve().parent.parent.parent / "models" / "classifier" / "CURRENT_MODEL"
)


def _read_current_model_s3_uri() -> str | None:
    """Read the S3 URI from the CURRENT_MODEL file."""
    if not CURRENT_MODEL_FILE.exists():
        return None
    uri = CURRENT_MODEL_FILE.read_text().strip()
    return uri if uri else None


def _parse_s3_prefix(s3_uri: str) -> str:
    """Extract the S3 key prefix from an s3:// URI."""
    # s3://kube-news-raw/models/classifier/v1/ -> models/classifier/v1/
    parts = s3_uri.replace("s3://", "").split("/", 1)
    return parts[1] if len(parts) > 1 else ""


def ensure_model_downloaded() -> str | None:
    """Ensure the current model is downloaded locally.

    Checks in order:
    1. CLASSIFIER_MODEL_PATH env var (explicit override)
    2. CURRENT_MODEL file pointing to S3
    3. Returns None if no model is configured

    Returns the local path to the model directory, or None.
    """
    # Explicit override — user points directly to a local model
    if CLASSIFIER_MODEL_PATH:
        if Path(CLASSIFIER_MODEL_PATH).exists():
            return CLASSIFIER_MODEL_PATH
        logger.warning(
            "CLASSIFIER_MODEL_PATH set but path doesn't exist: %s", CLASSIFIER_MODEL_PATH
        )
        return None

    # Read S3 URI from CURRENT_MODEL file
    s3_uri = _read_current_model_s3_uri()
    if not s3_uri:
        return None

    s3_prefix = _parse_s3_prefix(s3_uri)
    if not s3_prefix:
        return None

    # Determine local cache path based on version
    version = s3_prefix.rstrip("/").split("/")[-1]  # e.g., "v1"
    local_dir = os.path.join(LOCAL_CACHE_DIR, version)

    # Check if already cached (look for config.json as a sentinel)
    if os.path.exists(os.path.join(local_dir, "config.json")):
        logger.debug("Model already cached at %s", local_dir)
        return local_dir

    # Download from S3
    logger.info("Downloading model from s3://%s/%s to %s", S3_BUCKET, s3_prefix, local_dir)
    try:
        import boto3

        s3 = boto3.client("s3", region_name=AWS_REGION)
        os.makedirs(local_dir, exist_ok=True)

        paginator = s3.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=S3_BUCKET, Prefix=s3_prefix):
            for obj in page.get("Contents", []):
                key = obj["Key"]
                relative = key[len(s3_prefix) :]
                if not relative:
                    continue
                local_path = os.path.join(local_dir, relative)
                os.makedirs(os.path.dirname(local_path), exist_ok=True)
                s3.download_file(S3_BUCKET, key, local_path)

        logger.info("Model downloaded to %s", local_dir)
        return local_dir
    except Exception:
        logger.warning("Failed to download model from S3", exc_info=True)
        return None
