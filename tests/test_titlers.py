"""Titler tests: heuristic default, Ollama backend with fallback, retitle command."""

import io
import json
import urllib.error

import pytest

from akashic_codex import titlers
from akashic_codex.db import get_conversation, insert_conversation
from akashic_codex.ingest import save_session


def fake_ollama(reply):
    def urlopen(req, timeout=None):
        return io.BytesIO(json.dumps({"response": reply}).encode())

    return urlopen


def test_heuristic_uses_first_sentence():
    assert (
        titlers.make_title("Chose SQLite for storage. It is local.") == "Chose SQLite for storage"
    )


def test_heuristic_trims_long_sentence_to_word_boundary():
    title = titlers.make_title("word " * 40)
    assert len(title) <= titlers.TITLE_MAX_CHARS
    assert not title.endswith(" ")


def test_empty_summary_is_untitled():
    assert titlers.make_title("   ") == "Untitled"


def test_unknown_backend_raises(monkeypatch):
    monkeypatch.setattr(titlers, "TITLER", "nope")
    with pytest.raises(ValueError):
        titlers.make_title("A summary.")


def test_ollama_title_is_cleaned(monkeypatch):
    monkeypatch.setattr(titlers, "TITLER", "ollama:gemma4:12b")
    monkeypatch.setattr("urllib.request.urlopen", fake_ollama('"Picking A Database."\n'))
    assert titlers.make_title("Chose SQLite.") == "Picking A Database"


def test_ollama_failure_falls_back_to_heuristic(monkeypatch):
    def down(req, timeout=None):
        raise urllib.error.URLError("refused")

    monkeypatch.setattr(titlers, "TITLER", "ollama:gemma4:12b")
    monkeypatch.setattr("urllib.request.urlopen", down)
    assert titlers.make_title("Chose SQLite. More.") == "Chose SQLite"


def test_save_session_generates_title_from_summary(db_conn, mock_embed, monkeypatch):
    monkeypatch.setattr("akashic_codex.ingest.summarize", lambda log: "Fixing the hook. Done.")
    cid = save_session(db_conn, "s1", "log")
    assert get_conversation(db_conn, cid)["title"] == "Fixing the hook"


def test_retitle_only_touches_untitled_by_default(db_conn):
    keep = insert_conversation(db_conn, "My title", "log", summary="Other thing. x")
    fix = insert_conversation(db_conn, "Untitled", "log", summary="Tuning lights. x")
    result = titlers.retitle_store(db_conn)
    assert result["count"] == 1
    assert get_conversation(db_conn, keep)["title"] == "My title"
    assert get_conversation(db_conn, fix)["title"] == "Tuning lights"
    assert result["backup"].exists()


def test_retitle_all_rewrites_every_title(db_conn):
    cid = insert_conversation(db_conn, "Old", "log", summary="New topic. x")
    result = titlers.retitle_store(db_conn, all_rows=True)
    assert result["count"] == 1
    assert get_conversation(db_conn, cid)["title"] == "New topic"
