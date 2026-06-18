"""Database access layer.

Keep ALL SQLite-specific code in this one module. If you ever migrate to
Postgres, this is the only file that should need to change.
"""

import os
import sqlite3
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


def insert_conversation(conn: sqlite3.Connection, title: str, full_log: str) -> int:
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

    Returns
    -------
    int
        The auto-generated id of the new conversations row.
    """
    with conn:
        cur = conn.execute(
            "INSERT INTO conversations (title, full_log) VALUES (?, ?)", (title, full_log)
        )
    return cur.lastrowid


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
