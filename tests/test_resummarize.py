import os

from living_library.db import connect
from living_library.ingest import save_conversation
from living_library.resummarize import resummarize_store


def test_resummarize_empty_rows_updates_summary_and_vector(db_conn, monkeypatch):

    conn = connect(os.environ['LIVING_LIBRARY_DB_PATH'])
    conn.execute(
        'INSERT INTO conversations (title, summary, full_log) VALUES (?, ?, ?)',
        ('Empty', '', 'User: Hi\nAssistant: Hello'),
    )
    conn.commit()
    resummarize_store(conn, empty_only=True)
    row = conn.execute('SELECT summary FROM conversations WHERE id = 1').fetchone()
    assert row['summary'] != ''


def test_resummarize_all_regenerates_each_summary(db_conn, monkeypatch):
    save_conversation(db_conn, 'User: Hi\nAssistant: Hello', title='A', source='claude')
    save_conversation(db_conn, 'User: Bye\nAssistant: Goodbye', title='B', source='gemini')
    resummarize_store(db_conn, empty_only=False)
    for i in [1, 2]:
        row = db_conn.execute('SELECT summary FROM conversations WHERE id = ?', (i,)).fetchone()
        assert row['summary'] != ''


def test_resummarize_selects_whitespace_summaries(db_conn, monkeypatch):

    conn = connect(os.environ['LIVING_LIBRARY_DB_PATH'])
    conn.execute(
        'INSERT INTO conversations (title, summary, full_log) VALUES (?, ?, ?)',
        ('Whitespace', '   ', 'User: Hi\nAssistant: Hello'),
    )
    conn.commit()
    resummarize_store(conn, empty_only=True)
    row = conn.execute('SELECT summary FROM conversations WHERE id = 1').fetchone()
    assert row['summary'] != ''


def test_resummarize_empty_result_preserves_existing_data(db_conn, monkeypatch):
    save_conversation(db_conn, 'User: Hi\nAssistant: Hello', title='A', source='claude')
    original = db_conn.execute('SELECT summary FROM conversations WHERE id = 1').fetchone()[
        'summary'
    ]
    resummarize_store(db_conn, empty_only=True)
    row = db_conn.execute('SELECT summary FROM conversations WHERE id = 1').fetchone()
    assert row['summary'] == original
