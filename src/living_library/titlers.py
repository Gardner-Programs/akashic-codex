import json
import os
import re
import urllib.request
from urllib.error import URLError
from urllib.request import Request

from .embeddings import embed  # noqa: F401

LIVING_LIBRARY_TITLER = os.environ.get('LIVING_LIBRARY_TITLER', 'heuristic')
LIVING_LIBRARY_OLLAMA_HOST = os.environ.get('LIVING_LIBRARY_OLLAMA_HOST', 'http://localhost:11434')


def make_title(summary: str) -> str:
    backend = os.environ.get('LIVING_LIBRARY_TITLER', LIVING_LIBRARY_TITLER)
    if backend.startswith('ollama:'):
        model = backend.split(':', 1)[1]
        try:
            return _ollama(summary, model)
        except RuntimeError:
            return _heuristic(summary)
    if backend == 'heuristic':
        return _heuristic(summary)
    raise RuntimeError(f'Unknown titler backend: {backend}')


def _clean(text: str) -> str:
    text = text.strip()
    text = re.sub(r'^[\s\-\*]+', '', text)
    text = re.sub(r'[\s\-\*]+$', '', text)
    return text


def _heuristic(summary: str) -> str:
    if not summary or not summary.strip():
        return 'Untitled'
    sentences = re.split(r'(?<=[.!?])\s+', summary.strip())
    first = sentences[0].strip()
    first = _clean(first)
    if len(first) > 60:
        words = first.split()
        total = 0
        kept = []
        for w in words:
            if total + len(w) + 1 > 60:
                break
            kept.append(w)
            total += len(w) + 1
        first = ' '.join(kept) + '…'
    return first or 'Untitled'


def _ollama(summary: str, model: str) -> str:
    prompt = f'Give a concise title (max 60 chars) for this conversation summary:\n\n{summary}'
    data = json.dumps({'model': model, 'prompt': prompt, 'stream': False}).encode()
    req = Request(
        f'{LIVING_LIBRARY_OLLAMA_HOST}/api/generate',
        data=data,
        headers={'Content-Type': 'application/json'},
    )
    try:
        with urllib.request.urlopen(req) as resp:
            result = json.loads(resp.read())
            title = result.get('response', '').strip()
            return _clean(title) or _heuristic(summary)
    except URLError as e:
        raise RuntimeError(f'Ollama request failed: {e}') from e


def retitle_store(conn, all_rows: bool = False) -> dict:
    import os
    from pathlib import Path

    from .db import backup, list_for_retitle, set_title

    plan_rows = list_for_retitle(conn, only_untitled=not all_rows)
    plan = {'count': len(plan_rows)}
    if plan['count'] == 0:
        return plan
    backup_path = backup(conn, 'retitle')
    rows = list_for_retitle(conn, only_untitled=not all_rows)
    for row in rows:
        title = make_title(row['summary'] or '')
        set_title(conn, row['id'], title)
    from .db import prune_backups

    db_path = Path(conn.execute('PRAGMA database_list').fetchone()['file'])
    prune_backups(db_path, 'retitle', int(os.environ.get('LIVING_LIBRARY_BACKUP_RETENTION', '5')))
    return {'retitled': len(rows), 'backup': str(backup_path)}
