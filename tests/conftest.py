import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))


def fake_embed(text: str) -> list[float]:
    import hashlib

    h = hashlib.md5(text.encode()).digest()
    return [b / 255.0 for b in h] + [0.0] * (384 - 16)


@pytest.fixture
def mock_embed(monkeypatch):
    monkeypatch.setattr('living_library.ingest.embed', fake_embed)
    monkeypatch.setattr('living_library.search.embed', fake_embed)
    monkeypatch.setattr('living_library.reembed.embed', fake_embed)
    monkeypatch.setattr('living_library.resummarize.embed', fake_embed)
    monkeypatch.setattr('living_library.titlers.embed', fake_embed)


@pytest.fixture
def db_conn(tmp_path, mock_embed):
    os.environ['LIVING_LIBRARY_DB_PATH'] = str(tmp_path / 'test.db')
    from living_library.db import connect, init_db

    init_db(os.environ['LIVING_LIBRARY_DB_PATH'])
    conn = connect(os.environ['LIVING_LIBRARY_DB_PATH'])
    yield conn
    conn.close()


@pytest.fixture
def seeded_conn(db_conn):
    from living_library.ingest import save_conversation

    save_conversation(
        db_conn, 'User: Hello\nAssistant: Hi there!', title='Greeting', source='claude'
    )
    save_conversation(
        db_conn,
        'User: How do I use SQLite?\nAssistant: Use sqlite3 module.',
        title='SQLite help',
        source='gemini',
    )
    save_conversation(
        db_conn,
        'User: What is C sharp?\nAssistant: C# is a programming language.',
        title='C sharp basics',
        source='claude',
    )
    return db_conn
