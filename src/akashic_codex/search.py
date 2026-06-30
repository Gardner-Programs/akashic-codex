"""Search: the two-tier retrieval that makes the store useful.

Tier 1 (cheap): rank over summaries/titles/tags. Return a short list.
Tier 2 (expensive): load the full transcript only for a chosen match.

Hybrid search = keyword (FTS, precise) + semantic (vectors, catches rephrasing).
"""

import sqlite3

from akashic_codex import db
from akashic_codex.embeddings import MODEL_NAME, embed

CANDIDATE_POOL = 20


def assert_active_embedder(conn: sqlite3.Connection) -> None:
    """Refuse to search if the active model isn't the one that built the store."""
    stored = db.get_meta(conn, "embedding_model")
    if stored is not None and stored != MODEL_NAME:
        raise RuntimeError(
            f"This store's vectors were built with '{stored}', but the active "
            f"embedding model is '{MODEL_NAME}'. Searching would compare "
            f"incomparable vectors. Re-embed the store or restore the original model."
        )


def search(conn: sqlite3.Connection, query: str, limit: int = 5) -> list[dict]:
    """Hybrid search over stored conversations, returning lightweight results.

    Combines keyword search (FTS5) and semantic search (vector nearest-neighbor),
    fusing the two rankings with Reciprocal Rank Fusion. Each method contributes
    a wider candidate pool (CANDIDATE_POOL) that is fused and then trimmed to
    ``limit``. Never returns full_log.

    Parameters
    ----------
    conn : sqlite3.Connection
        Open database connection.
    query : str
        The search query.
    limit : int, optional
        Maximum number of results to return (default 5).

    Returns
    -------
    list[dict]
        Lightweight result rows (id, title, summary), most relevant first.
    """
    assert_active_embedder(conn)
    fts_rows = db.search_fts(conn, query, CANDIDATE_POOL)
    vec_rows = db.search_vectors(conn, embed(query), CANDIDATE_POOL)
    fts_ids = [row["id"] for row in fts_rows]
    vec_ids = [row["conversation_id"] for row in vec_rows]
    ranked_ids = fuse([fts_ids, vec_ids])[:limit]
    return [dict(db.get_summary_row(conn, id)) for id in ranked_ids]


def fuse(ranked_lists: list[list[int]], k: int = 60) -> list[int]:
    """Merge ranked id lists into one ranking via Reciprocal Rank Fusion.

    Each id scores the sum of 1 / (k + rank) across the lists it appears in, so
    ids found by multiple search methods rank higher and duplicates are merged.

    Parameters
    ----------
    ranked_lists : list[list[int]]
        Each inner list is conversation ids in rank order (best first).
    k : int, optional
        RRF damping constant; larger values flatten the weight of top ranks
        (default 60).

    Returns
    -------
    list[int]
        Conversation ids ordered by fused score, best first.
    """
    scores = {}
    for ranked_list in ranked_lists:
        for rank, id in enumerate(ranked_list):
            score = 1 / (k + rank)
            scores[id] = scores.get(id, 0) + score
    return sorted(scores, key=scores.get, reverse=True)
