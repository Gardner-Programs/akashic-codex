import os

import pytest

from living_library.mcp_server import mcp


@pytest.fixture
def mcp_store(tmp_path, monkeypatch, mock_embed):
    os.environ['LIVING_LIBRARY_DB_PATH'] = str(tmp_path / 'test.db')
    from living_library.db import init_db

    init_db(os.environ['LIVING_LIBRARY_DB_PATH'])
    from living_library.db import connect
    from living_library.ingest import save_conversation

    conn = connect(os.environ['LIVING_LIBRARY_DB_PATH'])
    save_conversation(
        conn,
        'User: How do I use SQLite?\nAssistant: Import sqlite3.',
        title='SQLite help',
        source='claude',
    )
    save_conversation(
        conn,
        'User: What is Python?\nAssistant: A programming language.',
        title='Python basics',
        source='gemini',
    )


def test_search_memory_returns_lightweight_rows(mcp_store):
    results = mcp._tool_manager._tools['search_memory'].fn(query='SQLite', limit=5)
    assert len(results) >= 1
    assert 'full_log' not in results[0]


def test_search_memory_finds_relevant_conversation(mcp_store):
    results = mcp._tool_manager._tools['search_memory'].fn(query='programming language', limit=5)
    assert len(results) >= 1
    assert results[0]['title'] == 'Python basics'


def test_get_conversation_returns_full_record(mcp_store):
    results = mcp._tool_manager._tools['search_memory'].fn(query='SQLite', limit=5)
    conv_id = results[0]['id']
    conv = mcp._tool_manager._tools['get_conversation'].fn(conv_id=conv_id)
    assert conv['title'] == 'SQLite help'
    assert 'full_log' in conv


def test_get_conversation_missing_id_raises(mcp_store):
    with pytest.raises(ValueError):
        mcp._tool_manager._tools['get_conversation'].fn(conv_id=999)
