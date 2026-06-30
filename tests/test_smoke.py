"""Smoke tests. Expand these as you implement each module.

Run with:  pytest
"""

import re

import pytest

from akashic_codex import __version__
from akashic_codex.db import (
    SCHEMA_PATH,
    get_conversation,
    get_meta,
    get_tags,
    insert_conversation,
    insert_vector,
    search_fts,
    search_vectors,
    set_meta,
)
from akashic_codex.embeddings import MODEL_NAME, embed
from akashic_codex.ingest import ensure_embedder_identity, save_conversation
from akashic_codex.search import assert_active_embedder, fuse, search


def test_package_imports():
    assert __version__


def test_save_then_search_roundtrip(db_conn):
    convo_id = insert_conversation(db_conn, "Test", "Testing")
    assert convo_id == 1
    convo = get_conversation(db_conn, convo_id)
    assert convo["title"] == "Test"
    assert convo["full_log"] == "Testing"


def test_init_db_creates_tables(db_conn):
    names = {
        r["name"] for r in db_conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    assert {"conversations", "tags", "conversation_tags"} <= names


def test_get_missing_returns_none(db_conn):
    assert get_conversation(db_conn, 999) is None


def test_search_returns_summaries_not_full_log(db_conn):
    insert_conversation(db_conn, "Talk about zebras", "the full transcript")
    result = search(db_conn, "zebras")
    assert len(result) == 1
    assert result[0]["title"] == "Talk about zebras"
    assert "full_log" not in result[0]


def test_embedding_dimension_matches_schema():
    model_dim = len(embed("any text"))
    schema_text = SCHEMA_PATH.read_text()
    schema_dim = int(re.search(r"FLOAT\[(\d+)\]", schema_text).group(1))
    assert model_dim == schema_dim


def test_semantic_search_ranks_by_meaning(db_conn):
    relevant = insert_conversation(db_conn, "How to debug a segfault in C", "x")
    other = insert_conversation(db_conn, "Best pasta recipes for dinner", "x")
    insert_vector(db_conn, relevant, embed("How to debug a segfault in C"))
    insert_vector(db_conn, other, embed("Best pasta recipes for dinner"))

    results = search_vectors(db_conn, embed("troubleshooting crashes from bad pointers"), limit=2)
    assert results[0]["conversation_id"] == relevant


def test_fuse_rewards_ids_in_multiple_lists():
    result = fuse([[1, 4, 7, 8], [9, 4, 1, 0]])
    assert set(result[:2]) == {1, 4}
    assert set(result[3:]) == {0, 8, 7}


def test_hybrid_search_finds_by_meaning(seeded_conn):
    c_search = search(seeded_conn, "C sharp")
    ids = [r["id"] for r in c_search]
    assert ids.index(1) < ids.index(2)
    assert ids.index(3) < ids.index(2)


def test_search_fts_handles_special_characters(db_conn):
    insert_conversation(db_conn, "Learning C# basics", "x")
    for q in ["C#", "what's this?", "", "   ", "* )  (:, ^+ -}{"]:
        results = search_fts(db_conn, q)
        assert isinstance(results, list)
    assert len(search_fts(db_conn, "C#")) == 1


def test_hybrid_search_finds_by_keyword(seeded_conn):
    cook_search = search(seeded_conn, "pasta")
    assert cook_search[0]["id"] == 2


def test_save_conversations(db_conn):
    conv_id = save_conversation(db_conn, "convo testing full log", "convo testing", "cli")
    convo = get_conversation(db_conn, conv_id)
    assert convo["title"] == "convo testing"
    assert convo["source"] == "cli"
    assert convo["full_log"] == "convo testing full log"
    assert convo["summary"] is not None


def test_save_conversations_searching(db_conn):
    conv_id = save_conversation(
        db_conn, "searching convo testing full log", "search convo testing", "cli"
    )
    my_search = search(db_conn, "searching")
    assert my_search is not None
    assert conv_id == my_search[0]["id"]


def test_tag_saving(db_conn):
    conv_id = save_conversation(db_conn, "tag testing full log tag test", "tag testing")
    tags = get_tags(db_conn, conv_id)
    assert "tag" in tags


def test_set_meta_then_get_meta_returns_value(db_conn):
    assert get_meta(db_conn, "testing") is None
    set_meta(db_conn, "testing", "test")
    assert get_meta(db_conn, "testing") == "test"


def test_set_meta_upserts_existing_key(db_conn):
    set_meta(db_conn, "testing", "test")
    assert get_meta(db_conn, "testing") == "test"
    set_meta(db_conn, "testing", "test2")
    assert get_meta(db_conn, "testing") == "test2"


def test_ensure_embedder_identity_stamps_fresh_store(db_conn):
    vector = [0.1]
    assert not ensure_embedder_identity(db_conn, vector)
    assert get_meta(db_conn, "embedding_model") == MODEL_NAME
    assert get_meta(db_conn, "embedding_dim") == str(len(vector))


def test_ensure_embedder_identity_is_idempotent(db_conn):
    vector = [0.1]
    vector2 = [0.2, 0.3]
    ensure_embedder_identity(db_conn, vector)
    assert get_meta(db_conn, "embedding_dim") == str(len(vector))
    ensure_embedder_identity(db_conn, vector2)
    assert get_meta(db_conn, "embedding_dim") == str(len(vector))


def test_search_guard_allows_matching_model(db_conn):
    set_meta(db_conn, "embedding_model", MODEL_NAME)
    assert assert_active_embedder(db_conn) is None


def test_search_guard_raises_on_model_mismatch(db_conn):
    set_meta(db_conn, "embedding_model", "testing_model")
    with pytest.raises(RuntimeError) as run_error:
        assert_active_embedder(db_conn)
    assert "testing_model" in str(run_error.value)


def test_search_guard_allows_unstamped_store(db_conn):
    assert assert_active_embedder(db_conn) is None


def test_save_conversation_stamps_embedder_identity(db_conn):
    save_conversation(db_conn, "full_log")
    assert get_meta(db_conn, "embedding_model") == MODEL_NAME
