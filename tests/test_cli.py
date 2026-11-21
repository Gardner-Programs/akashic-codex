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


def test_serve_mcp_launches_server(monkeypatch):
    ran = {}
    monkeypatch.setattr("akashic_codex.mcp_server.db.init_db", lambda *a, **k: None)
    monkeypatch.setattr(
        "akashic_codex.mcp_server.mcp.run", lambda *a, **k: ran.setdefault("ok", True)
    )
    run(monkeypatch, "serve_mcp")
    assert ran["ok"]


def test_serve_api_launches_server(monkeypatch):
    captured = {}
    monkeypatch.setattr("uvicorn.run", lambda *a, **k: captured.update(a=a, k=k))
    run(monkeypatch, "serve_api")
    assert captured["a"][0] == "akashic_codex.api:app"
    assert captured["k"]["port"] == 8000


def test_cli_reembed_with_yes_skips_prompt(cli_db, tmp_path, monkeypatch, capsys):
    run(monkeypatch, "init")
    convo = tmp_path / "c.txt"
    convo.write_text("We picked SQLite.", encoding="utf-8")
    run(monkeypatch, "save", str(convo))
    run(monkeypatch, "reembed", "--yes")
    out = capsys.readouterr().out
    assert "Re-embed 1 conversations" in out
    assert "Re-embedded 1 conversations" in out


def test_cli_reembed_aborts_without_confirmation(cli_db, monkeypatch, capsys):
    run(monkeypatch, "init")
    monkeypatch.setattr("builtins.input", lambda _prompt: "n")
    run(monkeypatch, "reembed")
    assert "Aborted" in capsys.readouterr().out


def test_cli_retitle_with_yes(cli_db, monkeypatch, capsys):
    run(monkeypatch, "init")
    run(monkeypatch, "retitle", "--yes")
    assert "Retitled 0 of 0 conversations" in capsys.readouterr().out


def test_cli_resummarize_with_yes(cli_db, monkeypatch, capsys):
    run(monkeypatch, "init")
    run(monkeypatch, "resummarize", "--empty", "--yes")
    out = capsys.readouterr().out
    assert "Resummarize empty summaries (0 rows)" in out
    assert "Resummarized 0 conversations" in out


def test_cli_resummarize_rejects_conflicting_scope(monkeypatch):
    with pytest.raises(SystemExit):
        run(monkeypatch, "resummarize", "--empty", "--all", "--yes")


def test_claude_hook_falls_back_when_summarizer_fails(cli_db, monkeypatch, tmp_path):
    import json

    run(monkeypatch, "init")
    monkeypatch.setenv("AKASHIC_MIN_SESSION_CHARS", "0")
    transcript = tmp_path / "transcript.jsonl"
    transcript.write_text(
        '{"type":"user","message":{"content":"Remember my SQLite choice."}}\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(cli, "claude_transcript_to_log", lambda _path: "Remember my SQLite choice.")
    monkeypatch.setattr(
        "akashic_codex.summarizers.summarize",
        lambda _log: (_ for _ in ()).throw(RuntimeError("offline")),
    )
    monkeypatch.setattr(
        sys,
        "stdin",
        type(
            "Input",
            (),
            {
                "read": lambda self: json.dumps(
                    {"session_id": "s1", "transcript_path": str(transcript)}
                )
            },
        )(),
    )

    run(monkeypatch, "claude-hook")

    conn = db.connect()
    row = conn.execute("SELECT full_log, summary, summarizer FROM conversations").fetchone()
    assert row["full_log"] == "Remember my SQLite choice."
    assert row["summary"]
    assert row["summarizer"] == "extractive"


def test_claude_hook_skips_sessions_below_minimum_length(cli_db, monkeypatch, tmp_path, capsys):
    import json

    run(monkeypatch, "init")
    monkeypatch.setenv("AKASHIC_MIN_SESSION_CHARS", "40")
    transcript = tmp_path / "transcript.jsonl"
    transcript.write_text("{}\n", encoding="utf-8")
    monkeypatch.setattr(cli, "claude_transcript_to_log", lambda _path: "User: pong")
    monkeypatch.setattr(
        sys,
        "stdin",
        type(
            "Input",
            (),
            {
                "read": lambda self: json.dumps(
                    {"session_id": "s1", "transcript_path": str(transcript)}
                )
            },
        )(),
    )

    run(monkeypatch, "claude-hook")

    conn = db.connect()
    assert conn.execute("SELECT COUNT(*) FROM conversations").fetchone()[0] == 0
    assert "Session below minimum length; skipped" in capsys.readouterr().out


def test_claude_hook_saves_sessions_at_minimum_length(cli_db, monkeypatch, tmp_path):
    import json

    run(monkeypatch, "init")
    monkeypatch.setenv("AKASHIC_MIN_SESSION_CHARS", "10")
    transcript = tmp_path / "transcript.jsonl"
    transcript.write_text("{}\n", encoding="utf-8")
    monkeypatch.setattr(cli, "claude_transcript_to_log", lambda _path: "User: useful conversation")
    monkeypatch.setattr("akashic_codex.summarizers.summarize", lambda _log: "Useful conversation")
    monkeypatch.setattr(
        sys,
        "stdin",
        type(
            "Input",
            (),
            {
                "read": lambda self: json.dumps(
                    {"session_id": "s1", "transcript_path": str(transcript)}
                )
            },
        )(),
    )

    run(monkeypatch, "claude-hook")

    conn = db.connect()
    assert conn.execute("SELECT COUNT(*) FROM conversations").fetchone()[0] == 1


def test_claude_hook_session_end_policy_updates_raw_log_then_refreshes(
    cli_db, monkeypatch, tmp_path
):
    import json

    run(monkeypatch, "init")
    monkeypatch.setenv("AKASHIC_MIN_SESSION_CHARS", "0")
    monkeypatch.setenv("AKASHIC_SUMMARY_POLICY", "session_end")
    monkeypatch.setattr(cli, "claude_transcript_to_log", lambda _path: "updated transcript")
    payload = {"session_id": "s-policy", "transcript_path": "unused"}

    # First Stop creates a searchable row.
    monkeypatch.setattr("akashic_codex.summarizers.summarize", lambda _log: "Initial summary")
    monkeypatch.setattr(
        sys, "stdin", type("Input", (), {"read": lambda self: json.dumps(payload)})()
    )
    run(monkeypatch, "claude-hook")
    conn = db.connect()
    original = conn.execute("SELECT summary, title FROM conversations").fetchone()
    original_vector = conn.execute("SELECT embedding FROM summary_vectors").fetchone()[0]

    # Later Stops only replace full_log and do not call the summarizer.
    monkeypatch.setattr(
        "akashic_codex.summarizers.summarize",
        lambda _log: (_ for _ in ()).throw(AssertionError("should be deferred")),
    )
    payload["hook_event_name"] = "Stop"
    monkeypatch.setattr(
        sys, "stdin", type("Input", (), {"read": lambda self: json.dumps(payload)})()
    )
    run(monkeypatch, "claude-hook")
    row = conn.execute("SELECT full_log, summary, title FROM conversations").fetchone()
    assert row["full_log"] == "updated transcript"
    assert row["summary"] == original["summary"]
    assert row["title"] == original["title"]
    updated_vector = conn.execute("SELECT embedding FROM summary_vectors").fetchone()[0]
    assert updated_vector == original_vector

    # SessionEnd refreshes the derived fields using the latest full transcript.
    monkeypatch.setattr("akashic_codex.summarizers.summarize", lambda _log: "Final summary")
    payload["hook_event_name"] = "SessionEnd"
    monkeypatch.setattr(
        sys, "stdin", type("Input", (), {"read": lambda self: json.dumps(payload)})()
    )
    run(monkeypatch, "claude-hook")
    assert conn.execute("SELECT summary FROM conversations").fetchone()[0] == "Final summary"
