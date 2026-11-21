"""Compact working-context construction and chunk-level recall."""

import sqlite3

from akashic_codex import db


def build_context(conn: sqlite3.Connection, conv_id: int, recent_turns: int = 4) -> dict | None:
    """Build a compact agent context from a conversation brief and recent turns.

    Older turns are represented by summary and message id, so an agent can fetch
    only the relevant detail with ``get_message_chunk`` when needed.
    """
    conversation = db.get_summary_row(conn, conv_id)
    if conversation is None:
        return None
    chunks = db.list_message_chunks(conn, conv_id)
    split = max(0, len(chunks) - max(0, recent_turns))
    recent = chunks[split:]
    return {
        "conversation_id": conv_id,
        "title": conversation["title"],
        "brief": conversation["summary"] or "",
        "older_turns": [
            {"message_id": row["id"], "summary": row["summary"]} for row in chunks[:split]
        ],
        "recent_turns": [
            {
                "message_id": row["id"],
                "summary": row["summary"],
                "content": db.get_message_chunk(conn, row["id"])["content"],
            }
            for row in recent
        ],
    }


def search_chunks(conn: sqlite3.Connection, query: str, limit: int = 10) -> list[dict]:
    """Search chunk summaries first and return message ids as retrieval pointers."""
    return [dict(row) for row in db.search_message_chunks(conn, query, limit)]


def get_message_chunk(conn: sqlite3.Connection, message_id: int) -> dict | None:
    """Load a complete turn chunk by its id after a summary match."""
    row = db.get_message_chunk(conn, message_id)
    return dict(row) if row is not None else None
