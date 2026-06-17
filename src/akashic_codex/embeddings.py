"""Embedding generation.

The single most important rule in this project: pick ONE embedding model and use
it for everything written to and queried against the store. Vectors from different
models live in different spaces and are NOT comparable. A local model keeps you
vendor-independent, which is the whole point of AkashicCodex.
"""

import os

from sentence_transformers import SentenceTransformer

MODEL_NAME = os.environ.get("AKASHIC_EMBEDDING_MODEL", "all-MiniLM-L6-v2")
_model = None


def embed(text: str) -> list[float]:
    """Turn text into a vector.

    TODO:
      - lazy-load a sentence-transformers model (cache it; loading is slow)
      - return model.encode(text) as a plain list of floats
      - all-MiniLM-L6-v2 returns 384 dimensions; match this in schema.sql
    """
    global _model
    if _model is None:
        _model = SentenceTransformer(MODEL_NAME)
    return _model.encode(text).tolist()
