"""CLI tests: drive init / save / search / show through the entry point.

Tests go through main() with a patched argv so the argparse wiring and dispatch
are exercised, not just the cmd_* bodies. The CLI opens its own connection
(db.connect / db.init_db take no injectable path), so cli_db redirects both at a
throwaway file database for isolation.
"""

import sys

import pytest

import akashic_codex.cli as cli
from akashic_codex import db


@pytest.fixture
def cli_db(tmp_path, monkeypatch, mock_embed):
    """Point the CLI's db.connect / db.init_db at a throwaway file db."""
    dbfile = str(tmp_path / "cli.db")
    real_connect = db.connect
    real_init = db.init_db
    monkeypatch.setattr(db, "connect", lambda *a, **k: real_connect(dbfile))
    monkeypatch.setattr(db, "init_db", lambda *a, **k: real_init(dbfile))
    return dbfile


def run(monkeypatch, *argv):
    """Invoke the CLI as if called from the shell with the given arguments."""
    monkeypatch.setattr(sys, "argv", ["akashic_codex", *argv])
    cli.main()


def test_cli_init(cli_db, monkeypatch, capsys):
    run(monkeypatch, "init")
    assert "Database Initialized" in capsys.readouterr().out


def test_cli_save(cli_db, tmp_path, monkeypatch, capsys):
    run(monkeypatch, "init")
    convo = tmp_path / "c.txt"
    convo.write_text("...", encoding="utf-8")
    run(monkeypatch, "save", str(convo), "--title", "...")
    assert "Conversation saved ID:" in capsys.readouterr().out


def test_cli_search(cli_db, monkeypatch, capsys):
    run(monkeypatch, "init")
    run(monkeypatch, "search", "1")
    assert "No matches found" in capsys.readouterr().out


def test_cli_show(cli_db, monkeypatch, capsys):
    run(monkeypatch, "init")
    with pytest.raises(SystemExit) as exc:
        run(monkeypatch, "show", "1")
    assert exc.value.code == 1
    assert "No conversation with id" in capsys.readouterr().err


def test_cli_roundtrip(cli_db, tmp_path, monkeypatch, capsys):
    run(monkeypatch, "init")
    convo = tmp_path / "c.txt"
    convo.write_text("We chose SQLite for local-first storage.", encoding="utf-8")

    run(monkeypatch, "save", str(convo), "--title", "DB choice")
    assert "Conversation saved ID: 1" in capsys.readouterr().out

    run(monkeypatch, "search", "what storage did we pick")
    out = capsys.readouterr().out
    assert "[1]" in out and "DB choice" in out

    run(monkeypatch, "show", "1")
    out = capsys.readouterr().out
    assert "DB choice" in out and "SQLite" in out
