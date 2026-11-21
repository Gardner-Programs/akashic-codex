"""Regenerate stored summaries and keep their search vectors in sync."""

import sqlite3

from akashic_codex import db
from akashic_codex.embeddings import embed
from akashic_codex.summarizers import SUMMARIZER, summarize


def plan_resummarize(conn: sqlite3.Connection, empty_only: bool = True) -> dict:
    """Describe the summaries selected for regeneration."""
    rows = db.list_for_resummarize(conn, empty_only=empty_only)
    return {"count": len(rows), "empty_only": empty_only, "summarizer": SUMMARIZER}


def resummarize_store(conn: sqlite3.Connection, empty_only: bool = True) -> dict:
    """Back up, regenerate selected summaries, and replace their vectors."""
    backup_path = db.backup(conn, "pre-resummarize")
    rows = db.list_for_resummarize(conn, empty_only=empty_only)
    generated = {row["id"]: summarize(row["full_log"]) for row in rows}
    if any(not summary or not summary.strip() for summary in generated.values()):
        raise RuntimeError("Summarizer returned an empty summary; no rows were changed")
    vectors = {conv_id: embed(summary) for conv_id, summary in generated.items()}
    original_logs = {row["id"]: row["full_log"] for row in rows}

    conn.execute("BEGIN IMMEDIATE")
    try:
        # Recompute any row whose transcript changed during the model pass.
        current = {row["id"]: row for row in db.list_for_resummarize(conn, empty_only=False)}
        for conv_id in list(generated):
            row = current.get(conv_id)
            if row is None:
                generated.pop(conv_id)
                vectors.pop(conv_id)
                continue
            if row["full_log"] != original_logs[conv_id]:
                generated[conv_id] = summarize(row["full_log"])
                if not generated[conv_id] or not generated[conv_id].strip():
                    raise RuntimeError("Summarizer returned an empty summary; no rows were changed")
                vectors[conv_id] = embed(generated[conv_id])
        for conv_id, summary in generated.items():
            conn.execute(
                "UPDATE conversations SET summary = ?, summarizer = ? WHERE id = ?",
                (summary, SUMMARIZER, conv_id),
            )
            db.delete_vector(conn, conv_id)
            db.insert_vector(conn, conv_id, vectors[conv_id])
        conn.commit()
    except BaseException:
        conn.rollback()
        raise
    return {"count": len(generated), "backup": backup_path}
