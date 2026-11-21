"""Re-embed tests: swap every vector onto the active model, atomically.

Embedding is faked so each test controls the vectors (and their dimension)
without loading the real model.
"""

import sqlite3

import pytest
import sqlite_vec

from akashic_codex import reembed
from akashic_codex.db import (
    backup,
    get_meta,
    insert_conversation,
    insert_vector,
    search_vectors,
    set_meta,
)
from akashic_codex.ingest import ensure_embedder_identity, save_conversation


def stored_vector(conn, conv_id):
    blob = conn.execute(
        "SELECT embedding FROM summary_vectors WHERE conversation_id = ?", (conv_id,)
    ).fetchone()[0]
    return blob


def seed(conn, n=3, dim=384):
    ids = []
    for i in range(n):
        cid = insert_conversation(conn, f"t{i}", "log", summary=f"summary {i}")
        insert_vector(conn, cid, [0.1] * dim)
        ids.append(cid)
    set_meta(conn, "embedding_model", "old-model")
    set_meta(conn, "embedding_dim", str(dim))
    return ids


def test_reembed_replaces_every_vector_with_active_model(db_conn, monkeypatch):
    ids = seed(db_conn)
    monkeypatch.setattr(reembed, "embed", lambda text: [0.5] * 384)
    result = reembed.reembed_store(db_conn)
    assert result["count"] == 3
    for cid in ids:
        assert stored_vector(db_conn, cid) == sqlite_vec.serialize_float32([0.5] * 384)


def test_reembed_stamps_new_identity(db_conn, monkeypatch):
    seed(db_conn)
    monkeypatch.setattr(reembed, "embed", lambda text: [0.5] * 384)
    reembed.reembed_store(db_conn)
    assert get_meta(db_conn, "embedding_model") == reembed.MODEL_NAME
    assert get_meta(db_conn, "embedding_dim") == "384"


def test_reembed_recreates_table_when_dimension_changes(db_conn, monkeypatch):
    ids = seed(db_conn)
    monkeypatch.setattr(reembed, "embed", lambda text: [0.2] * 8)
    result = reembed.reembed_store(db_conn)
    assert result["dim"] == 8
    assert get_meta(db_conn, "embedding_dim") == "8"
    hits = search_vectors(db_conn, [0.2] * 8, limit=10)
    assert sorted(row["conversation_id"] for row in hits) == ids


def test_reembed_failure_leaves_store_untouched(db_conn, monkeypatch):
    ids = seed(db_conn)
    calls = {"n": 0}

    def flaky(text):
        calls["n"] += 1
        if calls["n"] == 2:
            raise RuntimeError("model crashed")
        return [0.9] * 384

    monkeypatch.setattr(reembed, "embed", flaky)
    with pytest.raises(RuntimeError):
        reembed.reembed_store(db_conn)
    assert get_meta(db_conn, "embedding_model") == "old-model"
    for cid in ids:
        assert stored_vector(db_conn, cid) == sqlite_vec.serialize_float32([0.1] * 384)


def test_reembed_failure_inside_swap_rolls_back(db_conn, monkeypatch):
    ids = seed(db_conn)
    dims = iter([384, 384, 7])  # third conversation comes back at the wrong size
    monkeypatch.setattr(reembed, "embed", lambda text: [0.9] * next(dims))
    with pytest.raises(ValueError):
        reembed.reembed_store(db_conn)
    assert not db_conn.in_transaction
    assert get_meta(db_conn, "embedding_model") == "old-model"
    for cid in ids:
        assert stored_vector(db_conn, cid) == sqlite_vec.serialize_float32([0.1] * 384)


def test_reembed_includes_conversation_saved_mid_run(db_conn, monkeypatch):
    seed(db_conn, n=1)
    added = {}

    def embed_and_simulate_hook(text):
        if not added:
            added["id"] = insert_conversation(db_conn, "late", "log", summary="arrived mid-run")
        return [0.5] * 384

    monkeypatch.setattr(reembed, "embed", embed_and_simulate_hook)
    result = reembed.reembed_store(db_conn)
    assert result["count"] == 2
    assert stored_vector(db_conn, added["id"]) == sqlite_vec.serialize_float32([0.5] * 384)


def test_reembed_embeds_missing_summary_as_empty_text(db_conn, monkeypatch):
    insert_conversation(db_conn, "no summary", "log")
    seen = []
    monkeypatch.setattr(reembed, "embed", lambda text: seen.append(text) or [0.5] * 384)
    reembed.reembed_store(db_conn)
    assert seen == [""]


def test_plan_reembed_reports_without_changing_anything(db_conn):
    seed(db_conn, n=2)
    plan = reembed.plan_reembed(db_conn)
    assert plan == {
        "count": 2,
        "old_model": "old-model",
        "old_dim": 384,
        "new_model": reembed.MODEL_NAME,
        "cost": 0.0,
    }
    assert get_meta(db_conn, "embedding_model") == "old-model"


def test_ensure_embedder_identity_refuses_model_mismatch(db_conn):
    set_meta(db_conn, "embedding_model", "old-model")
    with pytest.raises(RuntimeError, match="old-model"):
        ensure_embedder_identity(db_conn, [0.1])


def test_save_on_mismatched_model_writes_nothing(db_conn, mock_embed):
    set_meta(db_conn, "embedding_model", "old-model")
    with pytest.raises(RuntimeError):
        save_conversation(db_conn, "User: hi. Assistant: hello.")
    assert db_conn.execute("SELECT COUNT(*) FROM conversations").fetchone()[0] == 0


def test_reembed_backs_up_before_changing_anything(db_conn, monkeypatch):
    seed(db_conn)
    monkeypatch.setattr(reembed, "embed", lambda text: [0.5] * 384)
    result = reembed.reembed_store(db_conn)
    snapshot = sqlite3.connect(result["backup"])
    try:
        model = snapshot.execute(
            "SELECT value FROM store_meta WHERE key = 'embedding_model'"
        ).fetchone()[0]
        count = snapshot.execute("SELECT COUNT(*) FROM conversations").fetchone()[0]
    finally:
        snapshot.close()
    assert model == "old-model"
    assert count == 3


def test_reembed_backup_survives_a_failed_run(db_conn, tmp_path, monkeypatch):
    seed(db_conn)

    def broken(text):
        raise RuntimeError("model crashed")

    monkeypatch.setattr(reembed, "embed", broken)
    with pytest.raises(RuntimeError):
        reembed.reembed_store(db_conn)
    assert list(tmp_path.glob("test.db.pre-reembed-*"))


def test_backup_refuses_in_memory_database():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    with pytest.raises(RuntimeError, match="in-memory"):
        backup(conn)


def test_backup_retains_newest_snapshots_per_label(db_conn, tmp_path, monkeypatch):
    monkeypatch.setenv("AKASHIC_BACKUP_RETENTION", "2")
    first = backup(db_conn, "pre-reembed")
    second = backup(db_conn, "pre-retitle")
    third = backup(db_conn, "pre-reembed")
    fourth = backup(db_conn, "pre-reembed")

    assert not first.exists()
    assert second.exists()
    assert third.exists()
    assert fourth.exists()
    assert len(list(tmp_path.glob("test.db.pre-reembed-*"))) == 2
    assert len(list(tmp_path.glob("test.db.pre-retitle-*"))) == 1
