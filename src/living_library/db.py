import logging
import os
import sqlite3
import uuid
from pathlib import Path

import sqlite_vec

SCHEMA_PATH = Path(__file__).with_name('schema.sql')
LOGGER = logging.getLogger(__name__)


def get_default_db_path() -> Path:
    """Get the default database path, preserving the legacy location temporarily."""
    configured = os.environ.get('LIVING_LIBRARY_DB_PATH') or os.environ.get('AKASHIC_DB_PATH')
    if configured:
        return Path(configured).expanduser()

    new_dir = Path.home() / '.living-library'
    legacy_dir = Path.home() / '.akashic'
    if not new_dir.exists() and legacy_dir.exists():
        legacy_path = legacy_dir / 'akashic.db'
        LOGGER.warning(
            'Using legacy database at %s. Living Library now defaults to %s; '
            'back up and manually migrate the database before moving it.',
            legacy_path,
            new_dir / 'living-library.db',
        )
        return legacy_path
    return new_dir / 'living-library.db'


def connect(db_path: str | Path | None = None) -> sqlite3.Connection:
    """Connect to SQLite and load the sqlite-vec extension."""
    path = str(db_path or get_default_db_path())
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    sqlite_vec.load(conn)
    return conn


def init_db(db_path: str | Path | sqlite3.Connection | None = None) -> None:
    """Initialize or migrate a Living Library database."""
    close = False
    if isinstance(db_path, sqlite3.Connection):
        conn = db_path
    else:
        conn = connect(db_path)
        close = True
    conn.executescript(SCHEMA_PATH.read_text(encoding='utf-8'))
    conn.commit()
    set_meta(conn, 'schema_version', '2')
    conn.commit()
    if close:
        conn.close()


def get_meta(conn: sqlite3.Connection, key: str) -> str | None:
    row = conn.execute('SELECT value FROM store_meta WHERE key = ?', (key,)).fetchone()
    return row['value'] if row else None


def set_meta(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        'INSERT INTO store_meta(key, value) VALUES (?, ?) '
        'ON CONFLICT(key) DO UPDATE SET value = excluded.value',
        (key, value),
    )


def insert_conversation(
    conn: sqlite3.Connection,
    title: str,
    full_log: str,
    summarizer: str | None = None,
    summary: str | None = None,
    source: str | None = None,
    session_id: str | None = None,
    thread_id: str | None = None,
) -> int:
    cursor = conn.execute(
        'INSERT INTO conversations '
        '(title, summary, source, summarizer, session_id, thread_id, full_log) '
        'VALUES (?, ?, ?, ?, ?, ?, ?)',
        (title or 'Untitled', summary, source, summarizer, session_id, thread_id, full_log),
    )
    conn.commit()
    conv_id = cursor.lastrowid
    replace_messages(conn, conv_id, full_log)
    conn.commit()
    return conv_id


def upsert_conversation(
    conn: sqlite3.Connection,
    session_id: str,
    title: str,
    full_log: str,
    summarizer: str | None = None,
    summary: str | None = None,
    source: str | None = None,
    thread_id: str | None = None,
) -> int:
    row = conn.execute(
        'SELECT id FROM conversations WHERE session_id = ?', (session_id,)
    ).fetchone()
    if row:
        conv_id = row['id']
        conn.execute(
            'UPDATE conversations SET title = ?, full_log = ?, '
            'summary = COALESCE(?, summary), source = COALESCE(?, source), '
            'summarizer = COALESCE(?, summarizer), thread_id = COALESCE(?, thread_id) '
            'WHERE id = ?',
            (title or 'Untitled', full_log, summary, source, summarizer, thread_id, conv_id),
        )
    else:
        conn.commit()
        cursor = conn.execute(
            'INSERT INTO conversations '
            '(title, summary, source, summarizer, session_id, thread_id, full_log) '
            'VALUES (?, ?, ?, ?, ?, ?, ?)',
            (title or 'Untitled', summary, source, summarizer, session_id, thread_id, full_log),
        )
        conv_id = cursor.lastrowid
    replace_messages(conn, conv_id, full_log)
    conn.commit()
    return conv_id


def get_conversation(
    conn: sqlite3.Connection, conv_id: int | None = None, session_id: str | None = None
):
    if conv_id is not None:
        row = conn.execute('SELECT * FROM conversations WHERE id = ?', (conv_id,)).fetchone()
    elif session_id is not None:
        row = conn.execute(
            'SELECT * FROM conversations WHERE session_id = ?', (session_id,)
        ).fetchone()
    else:
        return None
    return dict(row) if row else None


def list_conversations(conn: sqlite3.Connection, limit: int = 20) -> list[dict]:
    rows = conn.execute(
        'SELECT id, title, summary, source, created_at FROM conversations ORDER BY id DESC LIMIT ?',
        (limit,),
    ).fetchall()
    return [dict(row) for row in rows]


def insert_vector(conn: sqlite3.Connection, conv_id: int, vector: list[float]) -> None:
    conn.execute(
        'INSERT INTO summary_vectors(conversation_id, embedding) VALUES (?, ?)',
        (conv_id, sqlite_vec.serialize_float32(vector)),
    )


def delete_vector(conn: sqlite3.Connection, conv_id: int) -> None:
    conn.execute('DELETE FROM summary_vectors WHERE conversation_id = ?', (conv_id,))


def search_fts(conn: sqlite3.Connection, query: str, limit: int = 5) -> list[dict]:
    if not query or not query.strip():
        return []
    words = [word for word in query.strip().split() if word]
    fts_query = ' AND '.join(f'"{word.replace(chr(34), chr(34) * 2)}"' for word in words)
    try:
        rows = conn.execute(
            'SELECT rowid AS id FROM conversations_fts WHERE conversations_fts MATCH ? LIMIT ?',
            (fts_query, limit),
        ).fetchall()
    except sqlite3.OperationalError:
        return []
    return [dict(row) for row in rows]


def search_vectors(conn: sqlite3.Connection, vector: list[float], limit: int = 5) -> list[dict]:
    rows = conn.execute(
        'SELECT conversation_id '
        'FROM summary_vectors WHERE embedding MATCH ? '
        'AND k = ? ORDER BY distance',
        (sqlite_vec.serialize_float32(vector), limit),
    ).fetchall()
    return [dict(row) for row in rows]


def replace_all_vectors(
    conn: sqlite3.Connection,
    vectors: dict[int, list[float]],
    dimension: int,
    meta: dict[str, str] | None = None,
) -> None:
    conn.commit()
    conn.execute('BEGIN IMMEDIATE')
    try:
        conn.execute('DROP TABLE IF EXISTS summary_vectors')
        conn.execute(
            f'CREATE VIRTUAL TABLE summary_vectors USING vec0('
            f'conversation_id INTEGER PRIMARY KEY, embedding float[{dimension}])'
        )
        for conv_id, vector in vectors.items():
            conn.execute(
                'INSERT INTO summary_vectors(conversation_id, embedding) VALUES (?, ?)',
                (conv_id, sqlite_vec.serialize_float32(vector)),
            )
        if meta:
            for key, value in meta.items():
                set_meta(conn, key, value)
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def get_or_create_tag(conn: sqlite3.Connection, name: str) -> int:
    row = conn.execute('SELECT id FROM tags WHERE name = ?', (name,)).fetchone()
    if row:
        return row['id']
    cursor = conn.execute('INSERT INTO tags(name) VALUES (?)', (name,))
    return cursor.lastrowid


def link_conversation_tag(conn: sqlite3.Connection, conv_id: int, tag_id: int) -> None:
    conn.execute(
        'INSERT OR IGNORE INTO conversation_tags(conversation_id, tag_id) VALUES (?, ?)',
        (conv_id, tag_id),
    )


def get_tags(conn: sqlite3.Connection, conv_id: int) -> list[str]:
    rows = conn.execute(
        'SELECT tags.name FROM tags '
        'JOIN conversation_tags ON conversation_tags.tag_id = tags.id '
        'WHERE conversation_tags.conversation_id = ? ORDER BY tags.name',
        (conv_id,),
    ).fetchall()
    return [row['name'] for row in rows]


def replace_messages(conn: sqlite3.Connection, conv_id: int, full_log: str) -> None:
    conn.execute('DELETE FROM messages WHERE conversation_id = ?', (conv_id,))
    turns = []
    current = None
    import re

    for line in full_log.splitlines():
        match = re.match(
            r'^(User|Assistant|System|Tool)(?: \[model=([^\]]+)\])?:\s?(.*)$', line, re.I
        )
        if match:
            role = match.group(1).lower()
            model = match.group(2)
            if current:
                turns.append(current)
            current = [role, match.group(3), model]
        elif current is not None:
            current[1] += '\n' + line
    if current:
        turns.append(current)
    conn.executemany(
        'INSERT INTO messages(conversation_id, turn_index, role, content, model) '
        'VALUES (?, ?, ?, ?, ?)',
        [
            (conv_id, index, role, content, model)
            for index, (role, content, model) in enumerate(turns)
        ],
    )


def get_messages(conn: sqlite3.Connection, conv_id: int) -> list[dict]:
    rows = conn.execute(
        'SELECT turn_index, role, content, model FROM messages '
        'WHERE conversation_id = ? ORDER BY turn_index',
        (conv_id,),
    ).fetchall()
    return rows


def find_transcript_overlaps(conn: sqlite3.Connection, session_id: str, full_log: str) -> list[int]:
    normalized = ''.join(full_log.split())
    if len(normalized) < 200:
        return []
    rows = conn.execute(
        'SELECT id, full_log FROM conversations WHERE session_id != ? OR session_id IS NULL',
        (session_id,),
    ).fetchall()
    matches = []
    for row in rows:
        old = ''.join(row['full_log'].split())
        if len(old) >= 200 and (old in normalized or normalized in old):
            matches.append(row['id'])
    return matches


def assign_thread(conn: sqlite3.Connection, ids: list[int], thread_id: str) -> None:
    placeholders = ','.join('?' for _ in ids)
    conn.execute(
        f'UPDATE conversations SET thread_id = ? WHERE id IN ({placeholders})',
        (thread_id, *ids),
    )
    conn.commit()


def list_summaries(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute('SELECT id, summary FROM conversations').fetchall()
    return [dict(row) for row in rows]


def list_for_resummarize(conn: sqlite3.Connection, empty_only: bool) -> list[dict]:
    if empty_only:
        rows = conn.execute(
            "SELECT id, full_log FROM conversations WHERE summary IS NULL OR trim(summary) = ''"
        ).fetchall()
    else:
        rows = conn.execute('SELECT id, full_log FROM conversations').fetchall()
    return [dict(row) for row in rows]


def list_for_retitle(conn: sqlite3.Connection, only_untitled: bool) -> list[dict]:
    if only_untitled:
        rows = conn.execute(
            "SELECT id, summary FROM conversations WHERE title = 'Untitled'"
        ).fetchall()
    else:
        rows = conn.execute('SELECT id, summary FROM conversations').fetchall()
    return [dict(row) for row in rows]


def set_title(conn: sqlite3.Connection, conv_id: int, title: str) -> None:
    conn.execute('UPDATE conversations SET title = ? WHERE id = ?', (title, conv_id))
    conn.commit()


def backup(conn: sqlite3.Connection, operation: str) -> Path:
    db_path = Path(conn.execute('PRAGMA database_list').fetchone()['file'])
    conn.commit()
    timestamp = uuid.uuid4().hex[:12]
    backup_path = db_path.with_name(f'{db_path.stem}.pre-{operation}-{timestamp}.db')
    backup_conn = sqlite3.connect(backup_path)
    conn.backup(backup_conn)
    backup_conn.close()
    return backup_path


def prune_backups(db_path: Path, operation: str, retain: int) -> None:
    pattern = f'{db_path.stem}.pre-{operation}-*.db'
    backups = sorted(
        db_path.parent.glob(pattern), key=lambda path: path.stat().st_mtime, reverse=True
    )
    for old in backups[max(0, retain) :]:
        old.unlink()
