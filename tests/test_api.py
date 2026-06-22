"""API tests: exercise the endpoints in-process with FastAPI's TestClient.

TestClient (built on httpx) sends requests straight to the app, no real server
or port. For isolation we use the idiomatic FastAPI tool, dependency_overrides:
we replace get_conn with a version that connects to a throwaway temp database,
so tests never touch the real store. The override is registered before the test
and cleared after.
"""

import pytest
from fastapi.testclient import TestClient

from akashic_codex import db
from akashic_codex.api import app, get_conn

DUMMY_CONVERSATIONS = [
    {
        "full_log": "User: SQLite or Postgres? Assistant: SQLite for local single-user.",
        "title": "SQLite vs Postgres for local-first",
        "source": "claude",
    },
    {
        "full_log": "User: avoid blocking FastAPI? Assistant: plain def runs in a threadpool.",
        "title": "FastAPI blocking calls and threadpool",
        "source": "claude",
    },
    {
        "full_log": "User: keyword vs semantic? Assistant: terms vs meaning; hybrid fuses.",
        "title": "Keyword vs semantic search",
        "source": "gemini",
    },
    {
        "full_log": "User: quick pasta recipe? Assistant: aglio e olio with garlic, oil.",
        "title": "Quick aglio e olio recipe",
        "source": "ollama",
    },
    {
        "full_log": "User: how to structure commits? Assistant: feature and its tests together.",
        "title": "Commit structure for features",
        "source": "claude",
    },
]


@pytest.fixture
def client(tmp_path, mock_embed):
    """A TestClient wired to a fresh temp database via a dependency override."""
    db_path = str(tmp_path / "api.db")
    db.init_db(db_path)  # create the schema in the throwaway db

    def override_get_conn():
        # Same shape as the real get_conn, but pinned to the temp db.
        conn = db.connect(db_path)
        try:
            yield conn
        finally:
            conn.close()

    # Tell FastAPI: wherever an endpoint depends on get_conn, use this instead.
    app.dependency_overrides[get_conn] = override_get_conn

    # Note: instantiated WITHOUT `with`, so the lifespan (which would init the
    # real default db) does not run. The override + manual init above cover us.
    yield TestClient(app)

    app.dependency_overrides.clear()  # undo the override so other tests are clean


def test_post_conversation_returns_201_and_id(client):
    r = client.post("/conversations", json={"full_log": "hello world", "title": "Testing"})
    assert r.status_code == 201
    assert r.json() == {"id": 1}


def test_get_conversation_returns_full_record(client):
    client.post("/conversations", json={"full_log": "hello world", "title": "Testing"})
    r = client.get("/conversations/1")
    assert r.status_code == 200
    assert r.json()["full_log"] == "hello world"
    assert r.json()["title"] == "Testing"


def test_search_returns_matching_conversation(client):
    for c in DUMMY_CONVERSATIONS:
        client.post("/conversations", json=c)

    r = client.get("/search", params={"query": "recipe", "limit": 3})
    assert r.status_code == 200
    assert len(r.json()) <= 3
    assert any("aglio e olio" in row["title"] for row in r.json())


def test_get_missing_conversation_returns_404(client):
    r = client.get("/conversations/999")
    assert r.status_code == 404


def test_post_without_full_log_returns_422(client):
    r = client.post("/conversations", json={})
    assert r.status_code == 422
