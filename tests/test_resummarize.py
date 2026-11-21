"""Resummarize tests: repair empty summaries and refresh semantic vectors."""

import pytest
import sqlite_vec

from akashic_codex import resummarize
from akashic_codex.db import insert_conversation, insert_vector


def test_resummarize_empty_rows_updates_summary_and_vector(db_conn, monkeypatch):
    empty = insert_conversation(db_conn, "Empty", "recover this log", summary="")
    kept = insert_conversation(db_conn, "Kept", "leave this log", summary="Existing")
    insert_vector(db_conn, empty, [0.1] * 384)
    insert_vector(db_conn, kept, [0.1] * 384)
    monkeypatch.setattr(resummarize, "summarize", lambda log: f"Summary: {log}")
    monkeypatch.setattr(resummarize, "embed", lambda text: [0.7] * 384)

    result = resummarize.resummarize_store(db_conn)

    assert result["count"] == 1
    assert db_conn.execute("SELECT summary FROM conversations WHERE id = ?", (empty,)).fetchone()[0]
    assert (
        db_conn.execute("SELECT summary FROM conversations WHERE id = ?", (kept,)).fetchone()[0]
        == "Existing"
    )
    vector = db_conn.execute(
        "SELECT embedding FROM summary_vectors WHERE conversation_id = ?", (empty,)
    ).fetchone()[0]
    assert vector == sqlite_vec.serialize_float32([0.7] * 384)
    assert result["backup"].exists()


def test_resummarize_all_regenerates_each_summary(db_conn, monkeypatch):
    cid = insert_conversation(db_conn, "Title", "full transcript", summary="Old summary")
    insert_vector(db_conn, cid, [0.1] * 384)
    monkeypatch.setattr(resummarize, "summarize", lambda _log: "Fresh summary")
    monkeypatch.setattr(resummarize, "embed", lambda _text: [0.5] * 384)

    result = resummarize.resummarize_store(db_conn, empty_only=False)

    assert result["count"] == 1
    row = db_conn.execute("SELECT summary, summarizer FROM conversations").fetchone()
    assert row["summary"] == "Fresh summary"
    assert row["summarizer"] == resummarize.SUMMARIZER


def test_resummarize_selects_whitespace_summaries(db_conn, monkeypatch):
    cid = insert_conversation(db_conn, "Title", "full transcript", summary="  \n")
    insert_vector(db_conn, cid, [0.1] * 384)
    monkeypatch.setattr(resummarize, "summarize", lambda _log: "Fresh summary")
    monkeypatch.setattr(resummarize, "embed", lambda _text: [0.5] * 384)

    result = resummarize.resummarize_store(db_conn)

    assert result["count"] == 1
    assert db_conn.execute("SELECT summary FROM conversations").fetchone()[0] == "Fresh summary"


def test_resummarize_empty_result_preserves_existing_data(db_conn, monkeypatch):
    cid = insert_conversation(db_conn, "Title", "full transcript", summary="")
    insert_vector(db_conn, cid, [0.1] * 384)
    monkeypatch.setattr(resummarize, "summarize", lambda _log: "  ")

    with pytest.raises(RuntimeError, match="empty summary"):
        resummarize.resummarize_store(db_conn)

    assert db_conn.execute("SELECT summary FROM conversations").fetchone()[0] == ""
    vector = db_conn.execute(
        "SELECT embedding FROM summary_vectors WHERE conversation_id = ?", (cid,)
    ).fetchone()[0]
    assert vector == sqlite_vec.serialize_float32([0.1] * 384)
