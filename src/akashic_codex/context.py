"""Context builder for agent working memory.

Builds a compact context from stored conversations: conversation brief, older
turn summaries with ids, and recent full turns. Agents use this as bounded
working memory and fetch exact older details by id when needed.
"""

from akashic_codex import db


def build_context(conn, conv_id: int, recent_turns: int = 6) -> dict | None:
    """Build a compact context for a conversation.

    Returns a brief with:
      - conversation summary (the lightweight row)
      - older turn summaries with ids (for on-demand retrieval)
      - most recent N full turns with role and model labels

    Parameters
    ----------
    conn : sqlite3.Connection
        Open database connection.
    conv_id : int
        Id of the conversation to build context for.
    recent_turns : int, optional
        Number of recent full turns to include (default 6).

    Returns
    -------
    dict or None
        Context object with brief and recent turns, or None if conversation not found.
    """
    row = db.get_conversation(conn, conv_id)
    if row is None:
        return None

    messages = db.get_messages_with_chunks(conn, conv_id)

    total = len(messages)
    split_idx = max(0, total - max(0, recent_turns))

    older = messages[:split_idx]
    recent = messages[split_idx:]
    brief = row["summary"] or row["title"]

    return {
        "id": row["id"],
        "title": row["title"],
        "brief": brief,
        "source": row["source"],
        "created_at": row["created_at"],
        "older_turns": [
            {
                "id": msg["chunk_id"],
                "turn_index": msg["turn_index"],
                "summary": msg["chunk_summary"],
            }
            for msg in older
            if msg["chunk_id"] is not None and msg["chunk_summary"]
        ],
        "older_chunk_ids": [
            msg["chunk_id"] for msg in older if msg["chunk_id"] is not None and msg["chunk_summary"]
        ],
        "recent_turns": [
            {
                "role": msg["role"],
                "content": msg["content"],
                "model": msg["model"],
                "chunk_id": msg["chunk_id"],
            }
            for msg in recent
        ],
    }
