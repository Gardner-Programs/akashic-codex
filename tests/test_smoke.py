"""Smoke tests. Expand these as you implement each module.

Run with:  pytest
"""

import pytest

from akashic_codex import __version__
from akashic_codex.db import connect, get_conversation, init_db, insert_conversation


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


# TODO as you build:
#   test_init_db_creates_tables
#   test_save_then_search_roundtrip
#   test_search_returns_summaries_not_full_log
#   test_embedding_dimension_matches_schema
