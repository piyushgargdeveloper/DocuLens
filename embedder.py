"""Phase 3: sentence-transformers embedding wrapper."""

import logging
import os

import numpy as np
from sentence_transformers import SentenceTransformer

MODEL_NAME = "all-MiniLM-L6-v2"

_model: SentenceTransformer | None = None
_log = logging.getLogger("doculens.embedder")


def get_model() -> SentenceTransformer:
    """Load the embedding model once and reuse it."""
    global _model
    if _model is None:
        _log.info("Loading embedding model %s", MODEL_NAME)
        _model = SentenceTransformer(MODEL_NAME)
        _log.info("Embedding model ready")
    return _model


def embed(texts: list[str]) -> np.ndarray:
    model = get_model()
    vectors = model.encode(texts, convert_to_numpy=True, normalize_embeddings=True)
    return vectors.astype("float32")


# Prefetch: load the model at startup when PREFETCH_MODEL=1 (e.g. in
# Docker builds or production startup). This moves the ~2s load from the
# first user request to container start, improving cold-start latency.
# Lazy: only runs when get_model() is first called, not at import time.
_prefetch_called = False


def _maybe_prefetch() -> None:
    global _prefetch_called
    if not _prefetch_called:
        if os.environ.get("PREFETCH_MODEL", "").strip() == "1":
            get_model()
        _prefetch_called = True


# Wrap get_model to trigger lazy prefetch on first call
_original_get_model = get_model


def get_model() -> SentenceTransformer:
    _maybe_prefetch()
    return _original_get_model()
