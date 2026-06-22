"""Shared pytest fixtures, auto-discovered for every test in this directory."""

import pytest

from akashic_codex.db import connect, init_db, insert_conversation, insert_vector
from akashic_codex.embeddings import embed

EMBED_DIM = 384  # all-MiniLM-L6-v2 / the FLOAT[384] in schema.sql


def fake_embed(text: str) -> list[float]:
    return [0.1] * EMBED_DIM


@pytest.fixture
def db_conn(tmp_path):
    """A fresh, initialized, vector-capable connection, closed after the test."""
    db_path = str(tmp_path / "test.db")
    init_db(db_path)
    conn = connect(db_path)
    yield conn
    conn.close()


@pytest.fixture
def seeded_conn(db_conn):
    """db_conn pre-loaded with a few conversations and their embeddings."""
    rows = [
        ("Debugging a segfault in C", "..."),
        ("Best pasta recipes for dinner", "..."),
        ("Fixing memory corruption in C++", "..."),
    ]
    for title, log in rows:
        cid = insert_conversation(db_conn, title, log)
        insert_vector(db_conn, cid, embed(title))
    return db_conn


@pytest.fixture
def mock_embed(monkeypatch):
    monkeypatch.setattr("akashic_codex.ingest.embed", fake_embed)
    monkeypatch.setattr("akashic_codex.search.embed", fake_embed)
