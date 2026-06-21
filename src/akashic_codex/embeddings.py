"""Embedding generation.

The single most important rule in this project: the store uses exactly ONE
embedding model, consistently, for everything written and queried. Vectors from
different models live in different spaces and are NOT comparable, so they must
never be mixed. Which model is yours to choose (AKASHIC_EMBEDDING_MODEL), and a
local default keeps you vendor-independent. But the choice is fixed for a store's
lifetime: changing it means re-embedding every summary, not mixing old and new.
"""

import os

from sentence_transformers import SentenceTransformer

MODEL_NAME = os.environ.get("AKASHIC_EMBEDDING_MODEL", "all-MiniLM-L6-v2")
_model = None


def embed(text: str) -> list[float]:
    """Embed text into a fixed-length semantic vector.

    Uses one fixed local model (see MODEL_NAME) for the entire store; vectors
    from different models are not comparable. The model is lazy-loaded on first
    call and cached for reuse.

    Parameters
    ----------
    text : str
        The text to embed (a summary at ingest time, or a query at search time).

    Returns
    -------
    list[float]
        The embedding vector (384 dimensions for all-MiniLM-L6-v2). Its length
        must match the summary_vectors dimension in schema.sql.
    """
    global _model
    if _model is None:
        _model = SentenceTransformer(MODEL_NAME)
    return _model.encode(text).tolist()
