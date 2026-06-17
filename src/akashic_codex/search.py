"""Search: the two-tier retrieval that makes the store useful.

Tier 1 (cheap): rank over summaries/titles/tags. Return a short list.
Tier 2 (expensive): load the full transcript only for a chosen match.

Hybrid search = keyword (FTS, precise) + semantic (vectors, catches rephrasings).
"""

import sqlite3

from akashic_codex import db


def search(conn: sqlite3.Connection, query: str, limit: int = 3) -> list[dict]:
    """Search stored conversations and return ranked lightweight results.

    Currently keyword-only (FTS5 via db.search_fts). Semantic and hybrid ranking
    are layered in at later roadmap steps. Never returns full_log.

    Parameters
    ----------
    conn : sqlite3.Connection
        Open database connection.
    query : str
        The search query.
    limit : int, optional
        Maximum number of results to return (default 3).

    Returns
    -------
    list[dict]
        Lightweight result rows (id, title, summary), most relevant first.
    """
    rows = db.search_fts(conn, query, limit)
    return [dict(r) for r in rows]


def get_conversation(conversation_id: int) -> dict:
    """Load one full conversation by id (tier 2 -- call only on a confirmed match)."""
    raise NotImplementedError
