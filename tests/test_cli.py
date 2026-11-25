import io
import json
import os

import pytest

from living_library.cli import main


@pytest.fixture
def cli_db(tmp_path, monkeypatch, mock_embed):
    os.environ['LIVING_LIBRARY_DB_PATH'] = str(tmp_path / 'test.db')
    from living_library.db import init_db

    init_db(os.environ['LIVING_LIBRARY_DB_PATH'])


def run(monkeypatch, *argv):
    monkeypatch.setattr('sys.argv', ['living-library'] + list(argv))
    try:
        main()
    except SystemExit as e:
        if e.code != 0:
            raise


def test_cli_init(cli_db, monkeypatch, capsys):
    run(monkeypatch, 'init')
    out = capsys.readouterr().out
    assert 'Initialized database' in out


def test_cli_save(cli_db, tmp_path, monkeypatch, capsys):
    f = tmp_path / 'conv.txt'
    f.write_text('User: Hello\nAssistant: Hi!')
    run(monkeypatch, 'save', str(f), '--title', 'Test', '--source', 'claude')
    out = capsys.readouterr().out
    assert 'Saved.' in out


def test_cli_import_batches_conversations_and_structures_messages(
    cli_db, tmp_path, monkeypatch, capsys
):
    export = tmp_path / 'export.json'
    export.write_text(
        json.dumps(
            {
                'chat_messages': [
                    {'role': 'user', 'content': 'Hi'},
                    {'role': 'assistant', 'content': 'Hello!'},
                ]
            }
        )
    )
    run(monkeypatch, 'import', 'claude', str(export))
    out = capsys.readouterr().out
    assert 'Imported 1 conversations' in out


def test_cli_search(cli_db, monkeypatch, capsys):
    from living_library.db import connect
    from living_library.ingest import save_conversation

    conn = connect(os.environ['LIVING_LIBRARY_DB_PATH'])
    save_conversation(
        conn,
        'User: How do I use SQLite?\nAssistant: Import sqlite3.',
        title='SQLite',
        source='claude',
    )
    run(monkeypatch, 'search', 'SQLite')
    out = capsys.readouterr().out
    assert 'SQLite' in out


def test_cli_show(cli_db, monkeypatch, capsys):
    from living_library.db import connect
    from living_library.ingest import save_conversation

    conn = connect(os.environ['LIVING_LIBRARY_DB_PATH'])
    save_conversation(conn, 'User: Hi\nAssistant: Hello', title='Greeting', source='claude')
    run(monkeypatch, 'show', '1')
    out = capsys.readouterr().out
    assert 'User: Hi' in out


def test_cli_roundtrip(cli_db, tmp_path, monkeypatch, capsys):
    f = tmp_path / 'conv.txt'
    f.write_text('User: What is the capital of France?\nAssistant: Paris.')
    run(monkeypatch, 'save', str(f), '--title', 'Capital', '--source', 'gemini')
    run(monkeypatch, 'search', 'capital')
    out = capsys.readouterr().out
    assert 'Capital' in out


def test_serve_mcp_launches_server(monkeypatch):
    import living_library.mcp_server as mcp_module

    called = {}

    def fake_run(transport):
        called['transport'] = transport

    monkeypatch.setattr(mcp_module.mcp, 'run', fake_run)
    from living_library.cli import cmd_serve_mcp

    cmd_serve_mcp(type('Args', (), {})())
    assert called['transport'] == 'stdio'


def test_serve_api_launches_server(monkeypatch):
    import living_library.api as api_module

    called = {}

    def fake_run(app, host, port, reload):
        called['host'] = host
        called['port'] = port
        called['reload'] = reload

    monkeypatch.setattr(api_module.uvicorn, 'run', fake_run)
    from living_library.cli import cmd_serve_api

    cmd_serve_api(type('Args', (), {'host': '127.0.0.1', 'port': 8000, 'reload': False})())
    assert called['host'] == '127.0.0.1'
    assert called['port'] == 8000
    assert called['reload'] is False


def test_cli_reembed_with_yes_skips_prompt(cli_db, tmp_path, monkeypatch, capsys):
    from living_library.db import connect
    from living_library.ingest import save_conversation

    conn = connect(os.environ['LIVING_LIBRARY_DB_PATH'])
    save_conversation(conn, 'User: Hi\nAssistant: Hello', title='Test', source='claude')
    monkeypatch.setenv('LIVING_LIBRARY_EMBEDDING_MODEL', 'all-mpnet-base-v2')
    run(monkeypatch, 'reembed', '--yes')
    out = capsys.readouterr().out
    assert 'Re-embedded' in out


def test_cli_reembed_aborts_without_confirmation(cli_db, monkeypatch, capsys):
    from living_library.db import connect
    from living_library.ingest import save_conversation

    conn = connect(os.environ['LIVING_LIBRARY_DB_PATH'])
    save_conversation(conn, 'User: Hi\nAssistant: Hello', title='Test', source='claude')
    monkeypatch.setenv('LIVING_LIBRARY_EMBEDDING_MODEL', 'all-mpnet-base-v2')
    monkeypatch.setattr('builtins.input', lambda _: 'n')
    run(monkeypatch, 'reembed')
    out = capsys.readouterr().out
    assert 'Aborted' in out


def test_cli_retitle_with_yes(cli_db, monkeypatch, capsys):
    from living_library.db import connect
    from living_library.ingest import save_conversation

    conn = connect(os.environ['LIVING_LIBRARY_DB_PATH'])
    save_conversation(conn, 'User: Hi\nAssistant: Hello', title='Untitled', source='claude')
    run(monkeypatch, 'retitle', '--yes')
    out = capsys.readouterr().out
    assert 'Retitled' in out


def test_cli_resummarize_with_yes(cli_db, monkeypatch, capsys):
    from living_library.db import connect
    from living_library.ingest import save_conversation

    conn = connect(os.environ['LIVING_LIBRARY_DB_PATH'])
    save_conversation(conn, 'User: Hi\nAssistant: Hello', title='Test', source='claude')
    run(monkeypatch, 'resummarize', '--yes')
    out = capsys.readouterr().out
    assert 'Resummarized' in out


def test_cli_resummarize_rejects_conflicting_scope(monkeypatch):

    monkeypatch.setattr('sys.argv', ['living-library', 'resummarize', '--empty', '--all'])
    from living_library.cli import main

    with pytest.raises(SystemExit) as e:
        main()
    assert e.value.code != 0


def test_claude_hook_falls_back_when_summarizer_fails(cli_db, monkeypatch, tmp_path):
    monkeypatch.setenv('LIVING_LIBRARY_MIN_SESSION_CHARS', '0')
    monkeypatch.setenv('LIVING_LIBRARY_SUMMARIZER', 'ollama:ghost')
    payload = {'session_id': 'sess-1', 'transcript_path': str(tmp_path / 'transcript.jsonl')}
    (tmp_path / 'transcript.jsonl').write_text(
        '{"type": "user", "message": {"content": "Hi"}}\n'
        '{"type": "assistant", "message": {"content": "Hello"}}'
    )
    monkeypatch.setattr('sys.stdin', io.StringIO(json.dumps(payload)))
    import sys

    from living_library.cli import cmd_claude_hook

    old_stdin = sys.stdin
    sys.stdin = io.StringIO(json.dumps(payload))
    try:
        cmd_claude_hook(type('Args', (), {})())
    finally:
        sys.stdin = old_stdin
    from living_library.db import connect, get_conversation

    conn = connect(os.environ['LIVING_LIBRARY_DB_PATH'])
    row = get_conversation(conn, session_id='sess-1')
    assert row is not None
    assert row['summarizer'] == 'extractive'


def test_claude_hook_skips_sessions_below_minimum_length(cli_db, monkeypatch, tmp_path, capsys):
    monkeypatch.setenv('LIVING_LIBRARY_MIN_SESSION_CHARS', '500')
    payload = {'session_id': 'sess-short', 'transcript_path': str(tmp_path / 'short.jsonl')}
    (tmp_path / 'short.jsonl').write_text(
        '{"type": "user", "message": {"content": "Hi"}}\n'
        '{"type": "assistant", "message": {"content": "Hello"}}'
    )
    monkeypatch.setattr('sys.stdin', io.StringIO(json.dumps(payload)))
    import sys

    from living_library.cli import cmd_claude_hook

    old_stdin = sys.stdin
    sys.stdin = io.StringIO(json.dumps(payload))
    try:
        cmd_claude_hook(type('Args', (), {})())
    finally:
        sys.stdin = old_stdin
    out = capsys.readouterr().out
    assert 'Session too short' in out


def test_claude_hook_session_end_policy_updates_raw_log_then_refreshes(
    cli_db, monkeypatch, tmp_path
):
    monkeypatch.setenv('LIVING_LIBRARY_SUMMARY_POLICY', 'session_end')
    monkeypatch.setenv('LIVING_LIBRARY_MIN_SESSION_CHARS', '0')
    transcript = tmp_path / 'session.jsonl'
    transcript.write_text(
        '{"type": "user", "message": {"content": "Hello there, how are you doing today?"}}\n'
        '{"type": "assistant", "message": '
        '{"content": "I am doing well, thank you for asking!"}}'
    )
    monkeypatch.setattr(
        'sys.stdin',
        io.StringIO(json.dumps({'session_id': 'sess-policy', 'transcript_path': str(transcript)})),
    )
    import sys

    from living_library.cli import cmd_claude_hook

    old_stdin = sys.stdin
    sys.stdin = io.StringIO(
        json.dumps({'session_id': 'sess-policy', 'transcript_path': str(transcript)})
    )
    try:
        cmd_claude_hook(type('Args', (), {})())
    finally:
        sys.stdin = old_stdin
    from living_library.db import connect, get_conversation

    conn = connect(os.environ['LIVING_LIBRARY_DB_PATH'])
    row = get_conversation(conn, session_id='sess-policy')
    assert row is not None
    assert 'Hello there' in row['full_log']
    assert row['summary'] == ''
    transcript.write_text(
        '{"type": "user", "message": {"content": "Hello there, how are you doing today?"}}\n'
        '{"type": "assistant", "message": '
        '{"content": "I am doing well, thank you for asking!"}}\n'
        '{"type": "user", "message": {"content": "What is the capital of France?"}}\n'
        '{"type": "assistant", "message": {"content": "Paris is the capital."}}'
    )
    monkeypatch.setattr(
        'sys.stdin',
        io.StringIO(json.dumps({'session_id': 'sess-policy', 'transcript_path': str(transcript)})),
    )
    sys.stdin = io.StringIO(
        json.dumps({'session_id': 'sess-policy', 'transcript_path': str(transcript)})
    )
    try:
        cmd_claude_hook(type('Args', (), {})())
    finally:
        sys.stdin = old_stdin
    row = get_conversation(conn, session_id='sess-policy')
    assert 'capital of France' in row['full_log']
    assert row['summary'] != ''
