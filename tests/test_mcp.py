"""MCP tests: exercise the tool functions directly over a temp database.

The @mcp.tool() decorator returns the plain function, so the tools can be called
like ordinary functions, no protocol or transport harness needed. The tools call
db.connect() with no arguments (which points at the real default store), so the
fixture redirects db.connect at a throwaway temp database for isolation and
reuses the mock_embed fixture from conftest to stay offline and fast.
"""

import pytest

from akashic_codex import db
from akashic_codex.ingest import save_conversation
from akashic_codex.mcp_server import get_conversation, search_memory

DUMMY_CONVERSATIONS = [
    {
        "full_log": "User: SQLite or Postgres? Assistant: SQLite for local single-user.",
        "title": "SQLite vs Postgres for local-first",
        "source": "claude",
    },
    {
        "full_log": "User: quick pasta recipe? Assistant: aglio e olio with garlic, oil.",
        "title": "Quick aglio e olio recipe",
        "source": "ollama",
    },
]


@pytest.fixture
def mcp_store(tmp_path, monkeypatch, mock_embed):
    """Point the MCP tools at a fresh, pre-seeded temp db instead of the real store."""
    db_path = str(tmp_path / "mcp.db")
    db.init_db(db_path)

    # The tools call db.connect() with no args. Redirect it to the temp db, and
    # hand back a fresh connection per call so a tool closing one (it does, in a
    # finally) does not break a later call in the same test.
    real_connect = db.connect
    monkeypatch.setattr(db, "connect", lambda *a, **k: real_connect(db_path))

    seed = real_connect(db_path)
    for c in DUMMY_CONVERSATIONS:
        save_conversation(seed, c["full_log"], c["title"], c["source"])
    seed.close()
    return db_path


def test_search_memory_returns_lightweight_rows(mcp_store):
    results = search_memory("database")
    assert isinstance(results, list) and results
    for row in results:
        assert set(row) == {"id", "title", "summary"}
        assert "full_log" not in row


def test_search_memory_finds_relevant_conversation(mcp_store):
    results = search_memory("recipe")
    assert any("aglio e olio" in row["title"] for row in results)


def test_get_conversation_returns_full_record(mcp_store):
    convo = get_conversation(1)
    assert isinstance(convo, dict)
    assert convo["id"] == 1
    assert convo["title"] == "SQLite vs Postgres for local-first"
    assert "full_log" in convo and convo["full_log"]


def test_get_conversation_missing_id_raises(mcp_store):
    with pytest.raises(ValueError):
        get_conversation(999)
