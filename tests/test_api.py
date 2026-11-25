import os

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path, monkeypatch, mock_embed):
    os.environ['LIVING_LIBRARY_DB_PATH'] = str(tmp_path / 'test.db')
    from living_library.api import app
    from living_library.db import init_db

    init_db(os.environ['LIVING_LIBRARY_DB_PATH'])

    def override_get_conn():
        from living_library.db import connect

        conn = connect(os.environ['LIVING_LIBRARY_DB_PATH'])
        try:
            yield conn
        finally:
            conn.close()

    app.dependency_overrides[app.routes[0].dependant.dependencies[0].call] = override_get_conn
    return TestClient(app)


def test_post_conversation_returns_201_and_id(client):
    resp = client.post(
        '/conversations',
        json={'full_log': 'User: Hi\nAssistant: Hello', 'title': 'Test', 'source': 'claude'},
    )
    assert resp.status_code == 201
    assert 'id' in resp.json()


def test_get_conversation_returns_full_record(client):
    resp = client.post(
        '/conversations',
        json={'full_log': 'User: Hi\nAssistant: Hello', 'title': 'Test', 'source': 'claude'},
    )
    conv_id = resp.json()['id']
    resp = client.get(f'/conversations/{conv_id}')
    assert resp.status_code == 200
    data = resp.json()
    assert data['title'] == 'Test'
    assert data['full_log'] == 'User: Hi\nAssistant: Hello'


def test_search_returns_matching_conversation(client):
    client.post(
        '/conversations',
        json={
            'full_log': 'User: How do I use SQLite?\nAssistant: Import sqlite3.',
            'title': 'SQLite',
            'source': 'claude',
        },
    )
    resp = client.get('/search?query=SQLite&limit=5')
    assert resp.status_code == 200
    results = resp.json()
    assert len(results) >= 1
    assert results[0]['title'] == 'SQLite'


def test_recent_conversations_returns_limited_lightweight_rows(client):
    client.post(
        '/conversations',
        json={'full_log': 'User: Hi\nAssistant: Hello', 'title': 'A', 'source': 'claude'},
    )
    client.post(
        '/conversations',
        json={'full_log': 'User: Bye\nAssistant: Goodbye', 'title': 'B', 'source': 'gemini'},
    )
    resp = client.get('/conversations?limit=1')
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert 'full_log' not in data[0]


def test_store_ui_is_served(client):
    resp = client.get('/ui')
    assert resp.status_code == 200
    assert 'text/html' in resp.headers['content-type']


def test_get_missing_conversation_returns_422(client):
    resp = client.get('/conversations/999')
    assert resp.status_code == 404


def test_post_without_full_log_returns_422(client):
    resp = client.post('/conversations', json={'title': 'Test'})
    assert resp.status_code == 422
