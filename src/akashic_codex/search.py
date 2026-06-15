"""Search: the two-tier retrieval that makes the store useful.

Tier 1 (cheap): rank over summaries/titles/tags. Return a short list.
Tier 2 (expensive): load the full transcript only for a chosen match.

Hybrid search = keyword (FTS, precise) + semantic (vectors, catches rephrasings).
"""

import sqlite3

from akashic_codex import db


def search(conn: sqlite3.Connection, query: str, limit: int = 3) -> list[dict]:
    """Return ranked conversation summaries matching the query.

    TODO:
      - keyword: query conversations_fts (MATCH) for exact-ish hits
      - semantic: embeddings.embed(query), then nearest neighbours in summary_vectors
      - merge and de-duplicate the two result sets into one ranked list
      - return lightweight rows only (id, title, summary, tags, score) -- NOT full_log
    """
    rows = db.search_fts(conn, query, limit)
    return [dict(r) for r in rows]


def get_conversation(conversation_id: int) -> dict:
    """Load one full conversation by id (tier 2 -- call only on a confirmed match)."""
    raise NotImplementedError
