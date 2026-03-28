"""Classification: fine-tuned DistilBERT with zero-shot BART-MNLI fallback."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import httpx

from src.config import HF_API_TOKEN, USE_LOCAL_CLASSIFIER

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Zero-shot config (fallback)
# ---------------------------------------------------------------------------

HF_API_URL = "https://router.huggingface.co/hf-inference/models/facebook/bart-large-mnli"

CANDIDATE_LABELS = [
    "deprecation",
    "security",
    "feature",
    "release",
    "blog",
    "end of life",
]

# ---------------------------------------------------------------------------
# Local model state (lazy-loaded)
# ---------------------------------------------------------------------------

_local_model: Any = None
_local_tokenizer: Any = None
_local_label2id: dict[int, str] | None = None
_local_load_attempted = False


def _try_load_local_model() -> bool:
    """Attempt to load the fine-tuned DistilBERT model."""
    global _local_model, _local_tokenizer, _local_label2id, _local_load_attempted  # noqa: PLW0603
    _local_load_attempted = True

    try:
        from src.processing.model_loader import ensure_model_downloaded

        model_path = ensure_model_downloaded()
        if not model_path:
            return False

        from transformers import AutoModelForSequenceClassification, AutoTokenizer

        _local_tokenizer = AutoTokenizer.from_pretrained(model_path)
        _local_model = AutoModelForSequenceClassification.from_pretrained(model_path)
        _local_model.eval()

        # Load label mapping
        label_file = Path(model_path) / "label2id.json"
        if label_file.exists():
            label2id = json.loads(label_file.read_text())
            _local_label2id = {v: k for k, v in label2id.items()}
        else:
            _local_label2id = None

        logger.info("Loaded fine-tuned classifier from %s", model_path)
        return True
    except Exception:
        logger.warning(
            "Failed to load local classifier, will use zero-shot fallback", exc_info=True
        )
        return False


def _has_local_model() -> bool:
    """Check if the local model is available (lazy-loads on first call)."""
    if not _local_load_attempted:
        _try_load_local_model()
    return _local_model is not None


# ---------------------------------------------------------------------------
# Local classification
# ---------------------------------------------------------------------------


def _classify_local(text: str, threshold: float = 0.3) -> dict[str, Any]:
    """Classify text using the fine-tuned DistilBERT model."""
    import torch

    inputs = _local_tokenizer(
        text[:2000], truncation=True, padding=True, max_length=256, return_tensors="pt"
    )

    with torch.no_grad():
        outputs = _local_model(**inputs)
        probs = torch.nn.functional.softmax(outputs.logits, dim=-1)[0]

    scores_dict: dict[str, float] = {}
    for idx, prob in enumerate(probs.tolist()):
        label_name = _local_label2id.get(idx, f"label_{idx}") if _local_label2id else f"label_{idx}"
        scores_dict[label_name] = round(prob, 4)

    top_idx = int(probs.argmax())
    top_label = _local_label2id.get(top_idx, "unknown") if _local_label2id else "unknown"
    top_score = float(probs[top_idx])

    if top_score < threshold:
        top_label = "unknown"

    return {
        "label": top_label,
        "confidence": round(top_score, 4),
        "all_scores": scores_dict,
    }


# ---------------------------------------------------------------------------
# Zero-shot classification (fallback)
# ---------------------------------------------------------------------------


def _classify_zero_shot(text: str, threshold: float = 0.3) -> dict[str, Any]:
    """Classify text using zero-shot BART-MNLI via HuggingFace Inference API."""
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

    # New API returns: [{"label": "x", "score": 0.9}, ...] sorted by score desc
    # Old API returned: {"labels": [...], "scores": [...]}
    if isinstance(result, list):
        all_scores = {item["label"]: item["score"] for item in result}
        sorted_items = sorted(result, key=lambda x: x["score"], reverse=True)
        top_label = sorted_items[0]["label"] if sorted_items else "unknown"
        top_score = sorted_items[0]["score"] if sorted_items else 0.0
    else:
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


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def classify_text(text: str, threshold: float = 0.3) -> dict[str, Any]:
    """Classify text. Uses fine-tuned model if available, else zero-shot.

    Returns:
        {"label": str, "confidence": float, "all_scores": dict[str, float]}
    """
    if not text.strip():
        return {"label": "unknown", "confidence": 0.0, "all_scores": {}}

    if USE_LOCAL_CLASSIFIER and _has_local_model():
        return _classify_local(text, threshold)

    return _classify_zero_shot(text, threshold)


def classify_batch(texts: list[str], threshold: float = 0.3) -> list[dict[str, Any]]:
    """Classify multiple texts."""
    results = []
    for text in texts:
        try:
            result = classify_text(text, threshold=threshold)
        except (httpx.HTTPStatusError, Exception) as e:
            logger.warning("Classification failed for text: %s — %s", text[:80], e)
            result = {"label": "unknown", "confidence": 0.0, "all_scores": {}}
        results.append(result)
    return results
