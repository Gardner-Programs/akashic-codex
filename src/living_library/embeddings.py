import os
from functools import lru_cache

from sentence_transformers import SentenceTransformer

EMBEDDING_MODEL = os.environ.get('LIVING_LIBRARY_EMBEDDING_MODEL', 'all-MiniLM-L6-v2')
MODEL_NAME = EMBEDDING_MODEL
EMBEDDING_DIM = 384


@lru_cache(maxsize=1)
def _get_model(model_name: str):
    return SentenceTransformer(model_name)


def embed(text: str) -> list[float]:
    model_name = os.environ.get('LIVING_LIBRARY_EMBEDDING_MODEL', EMBEDDING_MODEL)
    model = _get_model(model_name)
    return model.encode(text, normalize_embeddings=True).tolist()


def get_embedder_identity() -> tuple[str, int]:
    model_name = os.environ.get('LIVING_LIBRARY_EMBEDDING_MODEL', EMBEDDING_MODEL)
    return model_name, EMBEDDING_DIM
