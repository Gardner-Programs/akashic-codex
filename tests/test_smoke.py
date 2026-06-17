"""Smoke tests. Expand these as you implement each module.

Run with:  pytest
"""

import re

import pytest

from akashic_codex import __version__
from akashic_codex.db import (
    SCHEMA_PATH,
    connect,
    get_conversation,
    init_db,
    insert_conversation,
    insert_vector,
    search_vectors,
)
from akashic_codex.embeddings import embed
from akashic_codex.search import fuse, search


def test_package_imports():
    assert __version__


@pytest.fixture
def db_conn(tmp_path):
    db_path = str(tmp_path / "test.db")
    init_db(db_path)
    conn = connect(db_path)
    yield conn
    conn.close()


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


# TODO as you build:
#   test_init_db_creates_tables
#   test_save_then_search_roundtrip
#   test_search_returns_summaries_not_full_log
#   test_embedding_dimension_matches_schema
