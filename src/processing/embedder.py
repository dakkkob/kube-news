"""Generate sentence embeddings using all-MiniLM-L6-v2."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sentence_transformers import SentenceTransformer

logger = logging.getLogger(__name__)

MODEL_NAME = "all-MiniLM-L6-v2"
EMBEDDING_DIM = 384


def _load_model() -> SentenceTransformer:
    """Load the embedding model (downloads ~80MB on first use)."""
    from sentence_transformers import SentenceTransformer

    logger.info("Loading embedding model: %s", MODEL_NAME)
    return SentenceTransformer(MODEL_NAME)


# Use st.cache_resource when running inside Streamlit (persists across reruns),
# otherwise fall back to a simple module-level singleton.
try:
    import streamlit as st

    _get_model = st.cache_resource(show_spinner="Loading embedding model...")(_load_model)
except (ImportError, RuntimeError):
    _model: SentenceTransformer | None = None

    def _get_model() -> SentenceTransformer:  # type: ignore[misc]
        global _model  # noqa: PLW0603
        if _model is None:
            _model = _load_model()
        return _model


def embed_text(text: str) -> list[float]:
    """Embed a single text string. Returns a 384-dim vector."""
    model = _get_model()
    embedding = model.encode(text, show_progress_bar=False)
    return embedding.tolist()  # type: ignore[no-any-return]


def embed_batch(texts: list[str], batch_size: int = 32) -> list[list[float]]:
    """Embed multiple texts. Returns list of 384-dim vectors."""
    model = _get_model()
    embeddings = model.encode(texts, batch_size=batch_size, show_progress_bar=False)
    result: list[list[float]] = [e.tolist() for e in embeddings]
    return result
