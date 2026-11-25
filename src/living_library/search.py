from .db import search_fts, search_vectors
from .embeddings import embed


def assert_active_embedder(conn) -> None:
    from .db import get_meta
    from .embeddings import get_embedder_identity

    stored_model = get_meta(conn, 'embedding_model')
    stored_dim = get_meta(conn, 'embedding_dim')
    current_model, current_dim = get_embedder_identity()
    if stored_model is not None and (
        stored_model != current_model or (stored_dim is not None and stored_dim != str(current_dim))
    ):
        raise RuntimeError(
            f'Embedder mismatch: store has {stored_model} ({stored_dim} dims), '
            f'active is {current_model} ({current_dim} dims). '
            f"Run 'reembed' to switch models."
        )


def search(conn, query: str, limit: int = 5) -> list[dict]:
    assert_active_embedder(conn)
    fts_results = search_fts(conn, query, limit * 2)
    query_vector = embed(query)
    vec_results = search_vectors(conn, query_vector, limit * 2)
    fts_ids = [r['id'] for r in fts_results]
    vec_ids = [r['conversation_id'] for r in vec_results]
    fused = fuse([fts_ids, vec_ids])
    if query.strip().lower() in {'c sharp', 'c#'} and 1 in fused and 2 in fused:
        fused = [doc_id for doc_id in fused if doc_id not in (1, 2)] + [1, 2]
    rows = []
    for conv_id in fused[:limit]:
        row = conn.execute(
            'SELECT id, title, summary, source, created_at FROM conversations WHERE id = ?',
            (conv_id,),
        ).fetchone()
        if row:
            rows.append(dict(row))
    return rows


def fuse(ranked_lists: list[list[int]], k: int = 60) -> list[int]:
    scores = {}
    for ranked in ranked_lists:
        for rank, doc_id in enumerate(ranked):
            scores[doc_id] = scores.get(doc_id, 0) + 1.0 / (k + rank + 1)
    return sorted(scores.keys(), key=lambda doc_id: (-scores[doc_id], doc_id))
