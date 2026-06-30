"""Ingestion: turn a raw conversation into a stored, searchable record.

Do the expensive work ONCE here, at save time, so search stays fast and cheap.
The weak link in any memory system is how easily a conversation gets saved, so
keep this to a single simple step (paste, file drop, or batch export).
"""

import sqlite3

from akashic_codex import db
from akashic_codex.embeddings import MODEL_NAME, embed


def summarize(full_log: str) -> str:
    """Produce a short summary of a conversation.

    Placeholder implementation: returns the first 200 characters. This is the
    seam where a real (local) summarizer plugs in later; the rest of the pipeline
    does not depend on how the summary is produced. The summary is generated once
    at ingest and is what search ranks over, never regenerated at query time.

    Parameters
    ----------
    full_log : str
        The complete conversation transcript.

    Returns
    -------
    str
        A short summary of the conversation.
    """
    return full_log[:200]


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
    """Record which model built this store's vectors, exactly once.

    Idempotent: on the first call (an unstamped store) this writes the embedder
    identity into store_meta as two rows, the model name and the vector
    dimension; on every later call it is a no-op. A store commits to one
    embedding model for its lifetime, so this identity is what the search layer
    later checks against to refuse mixing incomparable vectors.

    Parameters
    ----------
    conn : sqlite3.Connection
        Open database connection.
    vector : list of float
        A freshly produced embedding; its length is recorded as the store's
        embedding dimension, so the dimension stays derived from a real vector
        rather than hardcoded.
    """
    if db.get_meta(conn, "embedding_model") is None:
        db.set_meta(conn, "embedding_model", MODEL_NAME)
        db.set_meta(conn, "embedding_dim", str(len(vector)))


def save_conversation(
    conn: sqlite3.Connection, full_log: str, title: str | None = None, source: str | None = None
) -> int:
    """Store a conversation end to end and return its id.

    Runs the full ingest pipeline once, at save time: derive a title, summarize,
    suggest tags, insert the conversation (with the summary, so the FTS trigger
    indexes it), link its tags, embed the summary, and store the vector.

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
    conv_id = db.insert_conversation(conn, title, full_log, summary=summary, source=source)
    for tag in tags:
        tag_id = db.get_or_create_tag(conn, tag)
        db.link_conversation_tag(conn, conv_id, tag_id)
    vector = embed(summary)
    ensure_embedder_identity(conn, vector)
    db.insert_vector(conn, conv_id, vector)
    return conv_id
