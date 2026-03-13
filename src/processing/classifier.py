"""Zero-shot classification via HuggingFace Inference API."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from src.config import HF_API_TOKEN

logger = logging.getLogger(__name__)

HF_API_URL = "https://api-inference.huggingface.co/models/facebook/bart-large-mnli"

CANDIDATE_LABELS = [
    "deprecation",
    "security",
    "feature",
    "release",
    "blog",
    "end of life",
]


def classify_text(text: str, threshold: float = 0.3) -> dict[str, Any]:
    """Classify text using zero-shot BART-MNLI via HuggingFace Inference API.

    Returns:
        {"label": str, "confidence": float, "all_scores": dict[str, float]}
    """
    if not text.strip():
        return {"label": "unknown", "confidence": 0.0, "all_scores": {}}

    if not HF_API_TOKEN:
        logger.warning("HF_API_TOKEN not set, skipping classification")
        return {"label": "unknown", "confidence": 0.0, "all_scores": {}}

    # Truncate to avoid API limits (BART max ~1024 tokens)
    text = text[:1500]

    headers = {"Authorization": f"Bearer {HF_API_TOKEN}"}
    payload = {
        "inputs": text,
        "parameters": {"candidate_labels": CANDIDATE_LABELS},
    }

    response = httpx.post(HF_API_URL, json=payload, headers=headers, timeout=30.0)
    response.raise_for_status()
    result = response.json()

    labels: list[str] = result.get("labels", [])
    scores: list[float] = result.get("scores", [])
    all_scores = dict(zip(labels, scores, strict=False))

    top_label = labels[0] if labels else "unknown"
    top_score = scores[0] if scores else 0.0

    # Map "end of life" back to "eol" for consistency
    if top_label == "end of life":
        top_label = "eol"

    if top_score < threshold:
        top_label = "unknown"

    return {
        "label": top_label,
        "confidence": round(top_score, 4),
        "all_scores": {k: round(v, 4) for k, v in all_scores.items()},
    }


def classify_batch(texts: list[str], threshold: float = 0.3) -> list[dict[str, Any]]:
    """Classify multiple texts. Calls API per item (HF free tier has no batch endpoint)."""
    results = []
    for text in texts:
        try:
            result = classify_text(text, threshold=threshold)
        except httpx.HTTPStatusError as e:
            logger.warning(
                "Classification failed for text (status %s): %s",
                e.response.status_code,
                text[:80],
            )
            result = {"label": "unknown", "confidence": 0.0, "all_scores": {}}
        results.append(result)
    return results
