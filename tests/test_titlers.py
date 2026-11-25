from urllib.error import URLError

import pytest

from living_library.titlers import _heuristic, make_title, retitle_store


def fake_ollama(reply):
    def urlopen(req, timeout=None):
        class Resp:
            def read(self):
                import json

                return json.dumps({'response': reply}).encode()

            def __enter__(self):
                return self

            def __exit__(self, *args):
                pass

        return Resp()

    return urlopen


def test_heuristic_uses_first_sentence():
    assert _heuristic('First sentence. Second sentence.') == 'First sentence.'


def test_heuristic_trims_long_sentence_to_word_boundary():
    long = 'This is a very long sentence that exceeds the sixty character limit by quite a bit.'
    result = _heuristic(long)
    assert len(result) <= 60
    assert result.endswith('…')


def test_empty_summary_is_untitled():
    assert _heuristic('') == 'Untitled'
    assert _heuristic('   ') == 'Untitled'


def test_unknown_backend_raises(monkeypatch):
    monkeypatch.setenv('LIVING_LIBRARY_TITLER', 'unknown')
    with pytest.raises(RuntimeError):
        make_title('test')


def test_ollama_title_is_cleaned(monkeypatch):
    monkeypatch.setenv('LIVING_LIBRARY_TITLER', 'ollama:test')
    monkeypatch.setattr('urllib.request.urlopen', fake_ollama('  * Title with markdown  '))
    assert make_title('summary') == 'Title with markdown'


def test_ollama_failure_falls_back_to_heuristic(monkeypatch):
    monkeypatch.setenv('LIVING_LIBRARY_TITLER', 'ollama:test')

    def down(req, timeout=None):
        raise URLError('connection refused')

    monkeypatch.setattr('urllib.request.urlopen', down)
    assert make_title('First sentence. Second.') == 'First sentence.'


def test_save_session_generates_title_from_summary(db_conn, mock_embed, monkeypatch):
    from living_library.ingest import save_session

    monkeypatch.setenv('LIVING_LIBRARY_TITLER', 'heuristic')
    conv_id = save_session(db_conn, 'sess-1', 'User: Hi\nAssistant: Hello', source='claude')
    row = db_conn.execute('SELECT title FROM conversations WHERE id = ?', (conv_id,)).fetchone()
    assert row['title'] != 'Untitled'


def test_retitle_only_touches_untitled_by_default(db_conn):
    from living_library.ingest import save_conversation

    save_conversation(db_conn, 'User: Hi\nAssistant: Hello', title='Custom Title', source='claude')
    save_conversation(db_conn, 'User: Bye\nAssistant: Goodbye', title='Untitled', source='gemini')
    result = retitle_store(db_conn, all_rows=False)
    assert result['retitled'] == 1


def test_retitle_all_rewrites_every_title(db_conn):
    from living_library.ingest import save_conversation

    save_conversation(db_conn, 'User: Hi\nAssistant: Hello', title='Custom Title', source='claude')
    save_conversation(
        db_conn, 'User: Bye\nAssistant: Goodbye', title='Another Title', source='gemini'
    )
    result = retitle_store(db_conn, all_rows=True)
    assert result['retitled'] == 2
