import os

from .db import (
    backup,
    list_for_resummarize,
    replace_all_vectors,
)
from .embeddings import embed, get_embedder_identity
from .summarizers import summarize
from .titlers import make_title


def plan_resummarize(conn, empty_only: bool = True) -> dict:
    rows = list_for_resummarize(conn, empty_only)
    return {'count': len(rows)}


def resummarize_store(conn, empty_only: bool = True) -> dict:
    backup_path = backup(conn, 'resummarize')
    rows = list_for_resummarize(conn, empty_only)
    current_model, current_dim = get_embedder_identity()
    vectors = {}
    for row in rows:
        conv_id = row['id']
        full_log = row['full_log']
        summary = summarize(full_log)
        title = make_title(summary)
        conn.execute(
            'UPDATE conversations SET summary = ?, title = ?, summarizer = ? WHERE id = ?',
            (summary, title, os.environ.get('LIVING_LIBRARY_SUMMARIZER', 'extractive'), conv_id),
        )
        vectors[conv_id] = embed(summary)
    replace_all_vectors(
        conn,
        vectors,
        current_dim,
        meta={'embedding_model': current_model, 'embedding_dim': str(current_dim)},
    )
    from pathlib import Path

    from .db import prune_backups

    db_path = Path(conn.execute('PRAGMA database_list').fetchone()['file'])
    prune_backups(
        db_path, 'resummarize', int(os.environ.get('LIVING_LIBRARY_BACKUP_RETENTION', '5'))
    )
    return {'resummarized': len(vectors), 'backup': str(backup_path)}
