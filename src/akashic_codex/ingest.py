"""Ingestion: turn a raw conversation into a stored, searchable record.

Do the expensive work ONCE here, at save time, so search stays fast and cheap.
The weak link in any memory system is how easily a conversation gets saved, so
keep this to a single simple step (paste, file drop, or batch export).
"""

import sqlite3

from akashic_codex import db
from akashic_codex.embeddings import MODEL_NAME, embed
from akashic_codex.summarizers import SUMMARIZER, summarize


def suggest_tags(full_log: str) -> list[str]:
    """Propose topic tags from the conversation content.

    Placeholder implementation: returns the five most frequent words. A real
    tagger (stopword filtering or a model) can swap in later behind this seam.

    Parameters
    ----------
    full_log : str
        The complete conversation transcript.

    Returns
    -------
    list[str]
        Up to five suggested tag names.
    """
    common = {}
    for word in full_log.split():
        common[word] = common.get(word, 0) + 1
    return sorted(common, key=common.get, reverse=True)[:5]


def ensure_embedder_identity(conn: sqlite3.Connection, vector: list[float]) -> None:
    """Record which model built this store's vectors, and refuse to mix models.

    On the first call (an unstamped store) this writes the embedder identity
    into store_meta as two rows, the model name and the vector dimension. On
    every later call it checks the active model against the stored one and
    raises on a mismatch, so a save can never add a vector from a different
    model than the rest of the store. Search runs the same check on read.

    Parameters
    ----------
    conn : sqlite3.Connection
        Open database connection.
    vector : list of float
        A freshly produced embedding; its length is recorded as the store's
        embedding dimension, so the dimension stays derived from a real vector
        rather than hardcoded.

    Raises
    ------
    RuntimeError
        If the store was built with a different embedding model.
    """
    stored = db.get_meta(conn, "embedding_model")
    if stored is None:
        db.set_meta(conn, "embedding_model", MODEL_NAME)
        db.set_meta(conn, "embedding_dim", str(len(vector)))
    elif stored != MODEL_NAME:
        raise RuntimeError(
            f"This store's vectors were built with '{stored}', but the active "
            f"embedding model is '{MODEL_NAME}'. Saving would mix incomparable "
            f"vectors. Run `reembed` to move the store, or restore the original model."
        )


def save_conversation(
    conn: sqlite3.Connection, full_log: str, title: str | None = None, source: str | None = None
) -> int:
    """Store a conversation end to end and return its id.

    Runs the full ingest pipeline once, at save time: derive a title, summarize,
    suggest tags, embed the summary (refusing a model mismatch before anything is
    written), insert the conversation (with the summary, so the FTS trigger
    indexes it), link its tags, and store the vector.

    Parameters
    ----------
    conn : sqlite3.Connection
        Open database connection.
    full_log : str
        The complete conversation transcript.
    title : str or None, optional
        Title for the conversation; a default is used if not given.
    source : str or None, optional
        Which model or app the conversation came from.

    Returns
    -------
    int
        The id of the stored conversation.
    """
    if not title:
        title = "Untitled"
    summary = summarize(full_log)
    tags = suggest_tags(full_log)
    vector = embed(summary)
    ensure_embedder_identity(conn, vector)
    conv_id = db.insert_conversation(
        conn, title, full_log, summarizer=SUMMARIZER, summary=summary, source=source
    )
    for tag in tags:
        tag_id = db.get_or_create_tag(conn, tag)
        db.link_conversation_tag(conn, conv_id, tag_id)
    db.insert_vector(conn, conv_id, vector)
    return conv_id


def save_session(conn, session_id, full_log, title=None, source=None, thread_id=None) -> int:
    """Store or update a session's conversation end to end and return its id.

    The session-keyed sibling of save_conversation, used by the auto-save path:
    called once per turn with the same session_id as a live session grows, so it
    upserts (insert on the first turn, update in place after) instead of creating
    duplicate rows. Runs the full pipeline each time: summarize, suggest tags,
    upsert the conversation (with the summary, so the FTS triggers index it), link
    its tags, embed the summary, and replace the stored vector.

    Parameters
    ----------
    conn : sqlite3.Connection
        Open database connection.
    session_id : str
        Stable per-session id; the same value across a session's turns updates the
        one row rather than inserting a new one.
    full_log : str
        The complete conversation transcript as it stands this turn.
    title : str or None, optional
        Title for the conversation; a default is used if not given.
    source : str or None, optional
        Which model or app the conversation came from.
    thread_id : str or None, optional
        Logical conversation this session belongs to; None means its own thread.

    Returns
    -------
    int
        The id of the stored (inserted or updated) conversation.
    """
    if not title:
        title = "Untitled"
    summary = summarize(full_log)
    tags = suggest_tags(full_log)
    vector = embed(summary)
    ensure_embedder_identity(conn, vector)
    conv_id = db.upsert_conversation(
        conn,
        session_id,
        title,
        full_log,
        summarizer=SUMMARIZER,
        summary=summary,
        source=source,
        thread_id=thread_id,
    )
    for tag in tags:
        tag_id = db.get_or_create_tag(conn, tag)
        db.link_conversation_tag(conn, conv_id, tag_id)
    db.delete_vector(conn, conv_id)
    db.insert_vector(conn, conv_id, vector)
    return conv_id
