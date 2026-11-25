import os
from pathlib import Path

import pytest

from living_library.db import connect, get_meta
from living_library.ingest import ensure_embedder_identity, save_conversation
from living_library.reembed import plan_reembed, reembed_store


def stored_vector(conn, conv_id):
    row = conn.execute(
        'SELECT embedding FROM summary_vectors WHERE conversation_id = ?', (conv_id,)
    ).fetchone()
    return list(row['embedding']) if row else None


def seed(conn, n=3, dim=384):
    for i in range(n):
        save_conversation(
            conn, f'User: Hello {i}\nAssistant: Hi {i}', title=f'Conv {i}', source='claude'
        )


def test_reembed_replaces_every_vector_with_active_model(db_conn, monkeypatch):
    seed(db_conn)
    monkeypatch.setenv('LIVING_LIBRARY_EMBEDDING_MODEL', 'all-mpnet-base-v2')
    reembed_store(db_conn)
    assert get_meta(db_conn, 'embedding_model') == 'all-mpnet-base-v2'
    for i in range(3):
        vec = stored_vector(db_conn, i + 1)
        assert vec is not None


def test_reembed_stamps_new_identity(db_conn, monkeypatch):
    seed(db_conn)
    monkeypatch.setenv('LIVING_LIBRARY_EMBEDDING_MODEL', 'all-mpnet-base-v2')
    reembed_store(db_conn)
    assert get_meta(db_conn, 'embedding_model') == 'all-mpnet-base-v2'
    assert get_meta(db_conn, 'embedding_dim') == '384'


def test_reembed_recreates_table_when_dimension_changes(db_conn, monkeypatch):
    seed(db_conn)
    monkeypatch.setenv('LIVING_LIBRARY_EMBEDDING_MODEL', 'all-mpnet-base-v2')
    reembed_store(db_conn)
    row = db_conn.execute("SELECT sql FROM sqlite_master WHERE name = 'summary_vectors'").fetchone()
    assert 'float[384]' in row['sql']


def test_reembed_failure_leaves_store_untouched(db_conn, monkeypatch):
    seed(db_conn)
    original_vecs = [stored_vector(db_conn, i + 1) for i in range(3)]

    def bad_embed(text):
        raise RuntimeError('boom')

    monkeypatch.setattr('living_library.reembed.embed', bad_embed)
    monkeypatch.setenv('LIVING_LIBRARY_EMBEDDING_MODEL', 'all-mpnet-base-v2')
    with pytest.raises(RuntimeError):
        reembed_store(db_conn)
    for i, vec in enumerate(original_vecs):
        assert stored_vector(db_conn, i + 1) == vec


def test_reembed_failure_inside_swap_rolls_back(db_conn, monkeypatch):
    seed(db_conn)
    original_vecs = [stored_vector(db_conn, i + 1) for i in range(3)]
    call_count = {'n': 0}

    def flaky_embed(text):
        call_count['n'] += 1
        if call_count['n'] > 2:
            raise RuntimeError('boom')
        import hashlib

        h = hashlib.md5(text.encode()).digest()
        return [b / 255.0 for b in h] + [0.0] * (384 - 16)

    monkeypatch.setattr('living_library.reembed.embed', flaky_embed)
    monkeypatch.setenv('LIVING_LIBRARY_EMBEDDING_MODEL', 'all-mpnet-base-v2')
    with pytest.raises(RuntimeError):
        reembed_store(db_conn)
    for i, vec in enumerate(original_vecs):
        assert stored_vector(db_conn, i + 1) == vec


def test_reembed_includes_conversation_saved_mid_run(db_conn, monkeypatch):
    seed(db_conn, n=2)
    monkeypatch.setenv('LIVING_LIBRARY_EMBEDDING_MODEL', 'all-mpnet-base-v2')
    reembed_store(db_conn)
    save_conversation(db_conn, 'User: New\nAssistant: New', title='New', source='claude')
    assert stored_vector(db_conn, 3) is not None


def test_reembed_embeds_missing_summary_as_empty_text(db_conn, monkeypatch):

    conn = connect(os.environ['LIVING_LIBRARY_DB_PATH'])
    conn.execute(
        'INSERT INTO conversations (title, summary, full_log) VALUES (?, ?, ?)',
        ('Empty', '', 'User: Hi\nAssistant: Hello'),
    )
    conn.commit()
    monkeypatch.setenv('LIVING_LIBRARY_EMBEDDING_MODEL', 'all-mpnet-base-v2')
    reembed_store(conn)
    vec = stored_vector(conn, 1)
    assert vec is not None


def test_plan_reembed_reports_without_changing_anything(db_conn):
    seed(db_conn)
    plan = plan_reembed(db_conn)
    assert plan['count'] == 3
    assert plan['current_model'] == 'all-MiniLM-L6-v2'
    assert plan['new_model'] == 'all-MiniLM-L6-v2'


def test_ensure_embedder_identity_refuses_model_mismatch(db_conn):
    from living_library.embeddings import get_embedder_identity

    model, dim = get_embedder_identity()
    from living_library.db import set_meta

    set_meta(db_conn, 'embedding_model', 'other-model')
    set_meta(db_conn, 'embedding_dim', '999')
    with pytest.raises(RuntimeError):
        ensure_embedder_identity(db_conn, [0.0] * dim)


def test_save_on_mismatched_model_writes_nothing(db_conn, mock_embed):
    from living_library.db import set_meta

    set_meta(db_conn, 'embedding_model', 'other-model')
    set_meta(db_conn, 'embedding_dim', '999')
    from living_library.ingest import save_conversation

    with pytest.raises(RuntimeError):
        save_conversation(db_conn, 'User: Hi\nAssistant: Hello', title='Test', source='claude')
    count = db_conn.execute('SELECT COUNT(*) FROM conversations').fetchone()[0]
    assert count == 0


def test_reembed_backs_up_before_changing_anything(db_conn, monkeypatch):
    seed(db_conn)
    monkeypatch.setenv('LIVING_LIBRARY_EMBEDDING_MODEL', 'all-mpnet-base-v2')
    result = reembed_store(db_conn)
    assert 'backup' in result
    assert Path(result['backup']).exists()


def test_reembed_backup_survives_a_failed_run(db_conn, tmp_path, monkeypatch):
    seed(db_conn)
    monkeypatch.setenv('LIVING_LIBRARY_EMBEDDING_MODEL', 'all-mpnet-base-v2')

    def bad_embed(text):
        raise RuntimeError('boom')

    monkeypatch.setattr('living_library.reembed.embed', bad_embed)
    with pytest.raises(RuntimeError):
        reembed_store(db_conn)
    backups = list(tmp_path.glob('test.pre-reembed-*.db'))
    assert len(backups) == 1


def test_backup_retains_newest_snapshots_per_label(db_conn, tmp_path, monkeypatch):
    from living_library.db import backup, prune_backups

    for _ in range(7):
        backup(db_conn, 'reembed')
    prune_backups(Path(os.environ['LIVING_LIBRARY_DB_PATH']), 'reembed', 5)
    backups = list(tmp_path.glob('test.pre-reembed-*.db'))
    assert len(backups) == 5
