"""Database access layer.

Keep ALL SQLite-specific code in this one module. If you ever migrate to
Postgres, this is the only file that should need to change.
"""

import os
import sqlite3
from datetime import datetime
from pathlib import Path

import sqlite_vec

DB_PATH = os.environ.get("AKASHIC_DB_PATH", "data/akashic.db")
SCHEMA_PATH = Path(__file__).resolve().parents[2] / "schema.sql"


def connect(db_path: str = DB_PATH) -> sqlite3.Connection:
    """Open a SQLite connection configured for AkashicCodex.

    Applies per-connection setup that does not persist in the database file:
    enables foreign-key enforcement, sets row_factory so rows are accessible by
    column name, and loads the sqlite-vec extension so vector queries work. The
    parent directory is created if missing. The caller owns the returned
    connection and is responsible for closing it.

    Parameters
    ----------
    db_path : str, optional
        Path to the SQLite database file, created if it does not exist
        (default AKASHIC_DB_PATH).

    Returns
    -------
    sqlite3.Connection
        An open connection with foreign keys on, the Row factory set, and
        sqlite-vec loaded.
    """
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.row_factory = sqlite3.Row
    conn.enable_load_extension(True)
    sqlite_vec.load(conn)
    conn.enable_load_extension(False)
    return conn


def init_db(db_path: str = DB_PATH) -> None:
    """Create the schema if it does not already exist.

    Reads schema.sql and runs it against a fresh connection. Safe to call
    repeatedly: every statement uses CREATE ... IF NOT EXISTS. Opens and closes
    its own connection.

    Parameters
    ----------
    db_path : str, optional
        Path to the SQLite database file (default AKASHIC_DB_PATH).
    """
    schema = SCHEMA_PATH.read_text()
    conn = connect(db_path)
    try:
        with conn:
            conn.executescript(schema)
    finally:
        conn.close()


def insert_conversation(
    conn: sqlite3.Connection, title: str, full_log: str, summarizer=None, summary=None, source=None
) -> int:
    """Insert a conversation and return its new auto-generated id.

    The keyword-search index (conversations_fts) is kept in sync automatically
    by an AFTER INSERT trigger; the semantic vector is stored separately via
    insert_vector.

    Parameters
    ----------
    conn : sqlite3.Connection
        Open database connection.
    title : str
        Human-readable title (indexed for keyword search).
    full_log : str
        The complete transcript text.
    summarizer : str or None, optional
        Identifier of the summarizer backend that produced the summary,
        recorded as per-conversation provenance.
    summary : str or None, optional
        Short summary (indexed for keyword search; pass it here so the FTS
        trigger picks it up at insert time).
    source : str or None, optional
        Which model or app the conversation came from.

    Returns
    -------
    int
        The auto-generated id of the new conversations row.
    """
    with conn:
        cur = conn.execute(
            """INSERT INTO conversations (title, full_log, summarizer, summary, source)
            VALUES (?, ?, ?, ?, ?)""",
            (title, full_log, summarizer, summary, source),
        )
    return cur.lastrowid


def upsert_conversation(
    conn: sqlite3.Connection,
    session_id: str,
    title: str,
    full_log: str,
    summarizer=None,
    summary=None,
    source=None,
    thread_id=None,
) -> int:
    """Insert a conversation, or update the existing row for this session_id.

    The auto-save path calls this once per turn with the same session_id as a
    live session grows, so it must be an upsert (update in place) rather than a
    duplicate insert. Returns the conversation id either way. Manual saves that
    have no session go through insert_conversation instead; this function is the
    session-keyed path.

    Parameters
    ----------
    conn : sqlite3.Connection
        Open database connection.
    session_id : str
        Stable per-session id used as the conflict target; one client session
        maps to exactly one conversations row.
    title : str
        Human-readable title.
    full_log : str
        The complete transcript text as it stands this turn (overwrites the
        prior value on update).
    summarizer : str or None, optional
        Identifier of the summarizer backend that produced the summary.
    summary : str or None, optional
        Short summary (indexed for keyword search).
    source : str or None, optional
        Which model or app the conversation came from.
    thread_id : str or None, optional
        Logical conversation this session belongs to; None means the session is
        its own thread.

    Returns
    -------
    int
        The id of the inserted or updated conversations row.
    """
    with conn:
        row = conn.execute(
            """INSERT INTO conversations
            (session_id, title, full_log, summarizer, summary, source, thread_id)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(session_id) DO UPDATE SET
            title = excluded.title,
            full_log = excluded.full_log,
            summarizer = excluded.summarizer,
            summary = excluded.summary,
            source = excluded.source,
            thread_id = excluded.thread_id
            RETURNING id
            """,
            (session_id, title, full_log, summarizer, summary, source, thread_id),
        ).fetchone()
    return row["id"]


def get_or_create_tag(conn: sqlite3.Connection, name: str) -> int:
    """Return the id of a tag, creating it if it does not exist.

    The name is normalized (stripped and lowercased) so the same tag is not
    duplicated by case or surrounding whitespace, relying on the UNIQUE
    constraint on tags.name.

    Parameters
    ----------
    conn : sqlite3.Connection
        Open database connection.
    name : str
        The tag name.

    Returns
    -------
    int
        The id of the existing or newly created tag.
    """
    tag = name.strip().lower()
    with conn:
        conn.execute("INSERT OR IGNORE INTO tags (name) VALUES (?)", (tag,))
        row = conn.execute("SELECT id FROM tags WHERE name = ?", (tag,)).fetchone()
    return row["id"]


def get_tags(conn: sqlite3.Connection, conv_id: int) -> list[str]:
    """Return the tag names linked to a conversation.

    Joins conversation_tags to tags to resolve the many-to-many link into a flat
    list of tag names.

    Parameters
    ----------
    conn : sqlite3.Connection
        Open database connection.
    conv_id : int
        Id of the conversation whose tags to fetch.

    Returns
    -------
    list[str]
        The tag names linked to the conversation (empty if none).
    """
    rows = conn.execute(
        """SELECT t.name
        FROM tags t
        JOIN conversation_tags ct ON t.id = ct.tag_id
        WHERE ct.conversation_id = ?
        """,
        (conv_id,),
    ).fetchall()
    return [r["name"] for r in rows]


def link_conversation_tag(conn: sqlite3.Connection, conv_id: int, tag_id: int) -> None:
    """Link a conversation to a tag (idempotent).

    Inserts the (conversation_id, tag_id) pair into conversation_tags; a repeated
    link is ignored rather than raising.

    Parameters
    ----------
    conn : sqlite3.Connection
        Open database connection.
    conv_id : int
        Id of the conversation.
    tag_id : int
        Id of the tag.
    """
    with conn:
        conn.execute(
            "INSERT OR IGNORE INTO conversation_tags (conversation_id, tag_id) VALUES (?, ?)",
            (conv_id, tag_id),
        )


def get_conversation(conn: sqlite3.Connection, conv_id: int) -> sqlite3.Row | None:
    """Load one full conversation by id (the expensive tier-2 read).

    Call this only on a confirmed match, never for ranking; search returns
    lightweight rows instead.

    Parameters
    ----------
    conn : sqlite3.Connection
        Open database connection.
    conv_id : int
        Primary key of the conversation to load.

    Returns
    -------
    sqlite3.Row or None
        The complete record including full_log, or None if no row matches.
    """
    row = conn.execute(
        """SELECT id, title, summary, source, created_at, full_log
            FROM conversations
            WHERE id = ?""",
        (conv_id,),
    ).fetchone()
    return row


def get_summary_row(conn: sqlite3.Connection, conv_id: int) -> sqlite3.Row | None:
    """Load one conversation's lightweight fields by id (id, title, summary).

    Used to build search results from ranked ids without loading the full
    transcript (full_log), which keeps tier-1 search cheap.

    Parameters
    ----------
    conn : sqlite3.Connection
        Open database connection.
    conv_id : int
        Primary key of the conversation to load.

    Returns
    -------
    sqlite3.Row or None
        The lightweight row (id, title, summary), or None if no row matches.
    """
    row = conn.execute(
        """SELECT id, title, summary
            FROM conversations
            WHERE id = ?""",
        (conv_id,),
    ).fetchone()
    return row


def _sanitize_fts_query(query: str) -> str:
    """Quote each term so FTS5 treats the query as literal text.

    Wraps every whitespace-separated term in double quotes (doubling any internal
    quote to escape it), which neutralizes FTS5 query operators and special
    characters so arbitrary user input cannot raise a syntax error. This trades
    away FTS operator support: input is matched as plain AND-ed terms.
    """
    return " ".join('"' + word.replace('"', '""') + '"' for word in query.split())


def search_fts(conn: sqlite3.Connection, query: str, limit: int = 5) -> list[sqlite3.Row]:
    """Keyword search over title and summary via FTS5.

    Tier-1 search: returns lightweight rows only, never full_log. Multi-word
    queries are treated as AND (every term must match).

    Parameters
    ----------
    conn : sqlite3.Connection
        Open database connection.
    query : str
        Search terms; multiple words are AND-ed together.
    limit : int, optional
        Maximum number of rows to return (default 5).

    Returns
    -------
    list[sqlite3.Row]
        Rows of (id, title, summary) ranked by relevance, or an empty list when
        nothing matches.
    """
    sanitized = _sanitize_fts_query(query)
    if not sanitized:
        return []
    rows = conn.execute(
        """SELECT rowid AS id, title, summary
            FROM conversations_fts
            WHERE conversations_fts MATCH ?
            LIMIT ?""",
        (sanitized, limit),
    ).fetchall()
    return rows


def insert_vector(conn: sqlite3.Connection, conv_id: int, vector: list[float]) -> None:
    """Store a precomputed embedding vector for a conversation.

    The vector must already be produced by embeddings.embed (this layer does not
    embed), and its length must match the summary_vectors dimension. It is
    serialized to float32 bytes for sqlite-vec.

    Parameters
    ----------
    conn : sqlite3.Connection
        Open database connection.
    conv_id : int
        Id of the conversation the vector belongs to.
    vector : list[float]
        The precomputed embedding (length must match the schema dimension).
    """
    with conn:
        conn.execute(
            """INSERT INTO summary_vectors
            (conversation_id, embedding) VALUES (?, ?)""",
            (conv_id, sqlite_vec.serialize_float32(vector)),
        )


def delete_vector(conn: sqlite3.Connection, conv_id: int) -> None:
    """Remove a conversation's stored embedding vector, if it has one.

    Paired with insert_vector to replace a vector on the auto-save update path:
    summary_vectors.conversation_id is a primary key, so a changed summary
    cannot be re-inserted over the old vector directly. Delete the existing row
    first, then insert the fresh embedding. A no-op when no vector is stored.

    Parameters
    ----------
    conn : sqlite3.Connection
        Open database connection.
    conv_id : int
        Id of the conversation whose vector should be removed.
    """
    with conn:
        conn.execute(
            """DELETE FROM summary_vectors
            WHERE conversation_id = ?""",
            (conv_id,),
        )


def backup(conn: sqlite3.Connection, label: str = "backup") -> Path:
    """Write a consistent snapshot of the database next to the original file.

    Uses SQLite's online backup API, so the copy is consistent even if another
    process (such as the auto-save hook) writes during it. The file is named
    ``<db file>.<label>-<timestamp>`` in the same directory.

    Parameters
    ----------
    conn : sqlite3.Connection
        Open connection to a file-backed database.
    label : str, optional
        Short tag for the filename, such as "pre-reembed" (default "backup").

    Returns
    -------
    Path
        Path of the backup file.

    Raises
    ------
    RuntimeError
        If the database is in-memory and so has no file to back up next to.
    """
    db_file = conn.execute("PRAGMA database_list").fetchone()["file"]
    if not db_file:
        raise RuntimeError("Cannot back up an in-memory database")
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    dest = Path(f"{db_file}.{label}-{stamp}")
    target = sqlite3.connect(dest)
    try:
        conn.backup(target)
    finally:
        target.close()
    return dest


def list_summaries(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    """Return every conversation's id and summary, oldest first.

    The input to a full re-embed: summaries are what get embedded. A missing
    summary comes back as None; the caller decides how to embed it.

    Parameters
    ----------
    conn : sqlite3.Connection
        Open database connection.

    Returns
    -------
    list[sqlite3.Row]
        Rows of (id, summary) ordered by id.
    """
    return conn.execute("SELECT id, summary FROM conversations ORDER BY id").fetchall()


def replace_all_vectors(
    conn: sqlite3.Connection,
    vectors: dict[int, list[float]],
    dim: int,
    meta: dict[str, str] | None = None,
) -> None:
    """Atomically swap the whole vector table for a freshly built one.

    Drops summary_vectors, recreates it at ``dim``, inserts every vector, and
    writes any ``meta`` keys, all in one transaction. Either the store ends up
    entirely on the new vectors and identity, or nothing changes; two models'
    vectors are never mixed. Recreating the table (rather than updating rows) is
    what lets the dimension change.

    The caller must already hold the write lock (``BEGIN IMMEDIATE``) and owns
    the commit or rollback, so it can do a final consistency check inside the
    same transaction. See reembed.reembed_store.

    Parameters
    ----------
    conn : sqlite3.Connection
        Open database connection inside an open transaction.
    vectors : dict[int, list[float]]
        Conversation id to embedding; every vector must have length ``dim``.
    dim : int
        Dimension for the recreated vector column.
    meta : dict[str, str] or None, optional
        store_meta keys to upsert in the same transaction.

    Raises
    ------
    ValueError
        If any vector's length differs from ``dim``.
    """
    dim = int(dim)
    bad = [cid for cid, vec in vectors.items() if len(vec) != dim]
    if bad:
        raise ValueError(f"Vectors for ids {bad[:5]} do not have dimension {dim}")
    conn.execute("DROP TABLE IF EXISTS summary_vectors")
    conn.execute(
        f"""CREATE VIRTUAL TABLE summary_vectors USING vec0(
            conversation_id INTEGER PRIMARY KEY,
            embedding FLOAT[{dim}]
        )"""
    )
    conn.executemany(
        "INSERT INTO summary_vectors (conversation_id, embedding) VALUES (?, ?)",
        [(cid, sqlite_vec.serialize_float32(vec)) for cid, vec in vectors.items()],
    )
    for key, value in (meta or {}).items():
        conn.execute(
            """INSERT INTO store_meta (key, value) VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value""",
            (key, value),
        )


def search_vectors(
    conn: sqlite3.Connection, query_vector: list[float], limit: int = 5
) -> list[sqlite3.Row]:
    """Semantic nearest-neighbor search over stored summary vectors.

    Takes a precomputed query vector and returns the closest conversations,
    nearest first (smaller distance means more similar). Lightweight rows only;
    load full records separately.

    Parameters
    ----------
    conn : sqlite3.Connection
        Open database connection.
    query_vector : list[float]
        The precomputed embedding of the search query.
    limit : int, optional
        Maximum number of matches to return (default 5).

    Returns
    -------
    list[sqlite3.Row]
        Rows of (conversation_id, distance) ordered nearest first.
    """
    rows = conn.execute(
        """SELECT conversation_id, distance
            FROM summary_vectors
            WHERE embedding MATCH ?
            ORDER BY distance
            LIMIT ?""",
        (sqlite_vec.serialize_float32(query_vector), limit),
    ).fetchall()
    return rows


def set_meta(conn: sqlite3.Connection, key: str, value: str) -> None:
    """Write a store-level metadata value, creating or overwriting the key.

    Generic key/value setter for the store_meta table; this layer stays
    decoupled from what the keys mean (embedder identity, schema version, and
    so on). Upserts on the key, so calling it again for an existing key
    overwrites the value rather than raising a UNIQUE constraint error.

    Parameters
    ----------
    conn : sqlite3.Connection
        Open database connection.
    key : str
        The metadata key (for example "embedding_model").
    value : str
        The value to store; always text.
    """
    with conn:
        conn.execute(
            """INSERT INTO store_meta
            (key, value) VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value""",
            (key, value),
        )


def get_meta(conn: sqlite3.Connection, key: str) -> str | None:
    """Read a store-level metadata value by key.

    Generic key/value getter for the store_meta table. Returns the stored
    value as text, or None if the key has never been set.

    Parameters
    ----------
    conn : sqlite3.Connection
        Open database connection.
    key : str
        The metadata key to look up.

    Returns
    -------
    str or None
        The stored value, or None if the key is absent.
    """
    row = conn.execute(
        """SELECT value
            FROM store_meta
            WHERE key = ?
            """,
        (key,),
    ).fetchone()
    return row["value"] if row else None
