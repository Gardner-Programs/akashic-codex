import os

from .db import (
    backup,
    get_meta,
    list_summaries,
    replace_all_vectors,
)
from .embeddings import embed, get_embedder_identity


def _embed_all(rows, cache: dict[str, list[float]]) -> dict[int, list[float]]:
    vectors = {}
    for row in rows:
        summary = row['summary'] or ''
        if summary not in cache:
            cache[summary] = embed(summary)
        vectors[row['id']] = cache[summary]
    return vectors


def plan_reembed(conn) -> dict:
    current_model, current_dim = get_embedder_identity()
    stored_model = get_meta(conn, 'embedding_model')
    stored_dim = get_meta(conn, 'embedding_dim')
    rows = list_summaries(conn)
    return {
        'count': len(rows),
        'current_model': stored_model or 'unknown',
        'new_model': current_model,
        'dimension_change': stored_dim != str(current_dim) if stored_dim else False,
    }


def reembed_store(conn) -> dict:
    backup_path = backup(conn, 'reembed')
    rows = list_summaries(conn)
    cache = {}
    vectors = _embed_all(rows, cache)
    current_model, current_dim = get_embedder_identity()
    replace_all_vectors(
        conn,
        vectors,
        current_dim,
        meta={'embedding_model': current_model, 'embedding_dim': str(current_dim)},
    )
    from pathlib import Path

    from .db import prune_backups

    db_path = Path(conn.execute('PRAGMA database_list').fetchone()['file'])
    prune_backups(db_path, 'reembed', int(os.environ.get('LIVING_LIBRARY_BACKUP_RETENTION', '5')))
    return {'reembedded': len(vectors), 'backup': str(backup_path)}
