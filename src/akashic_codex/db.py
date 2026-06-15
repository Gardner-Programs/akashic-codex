"""Database access layer.

Keep ALL SQLite-specific code in this one module. If you ever migrate to
Postgres, this is the only file that should need to change.
"""

import os
import sqlite3
from pathlib import Path

DB_PATH = os.environ.get("AKASHIC_DB_PATH", "data/akashic.db")
SCHEMA_PATH = Path(__file__).resolve().parents[2] / "schema.sql"


def connect(db_path: str = DB_PATH) -> sqlite3.Connection:
    """Open a connection with sane defaults.

    TODO:
      - enable foreign keys: conn.execute("PRAGMA foreign_keys = ON")
      - set row_factory = sqlite3.Row so rows behave like dicts
      - load the sqlite-vec extension here (conn.enable_load_extension(True), then
        import sqlite_vec; sqlite_vec.load(conn)) so vector queries work
    """
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_path: str = DB_PATH) -> None:
    """Create the schema if it does not exist.

    TODO: read schema.sql and executescript() it against a fresh connection.
    """
    schema = SCHEMA_PATH.read_text()
    conn = connect(db_path)
    try:
        with conn:
            conn.executescript(schema)
    finally:
        conn.close()


def insert_conversation(conn: sqlite3.Connection, title: str, full_log: str) -> int:
    """Inserts a conversation into the database."""
    with conn:
        cur = conn.execute(
            "INSERT INTO conversations (title, full_log) VALUES (?, ?)", (title, full_log)
        )
    return cur.lastrowid


def get_conversation(conn: sqlite3.Connection, conv_id: int) -> sqlite3.Row | None:
    """Retrieves a conversation from the database."""
    row = conn.execute(
        """SELECT id, title, summary, source, created_at, full_log
            FROM conversations
            WHERE id = ?""",
        (conv_id,),
    ).fetchone()
    return row


def search_fts(conn: sqlite3.Connection, query: str, limit: int = 3) -> list[sqlite3.Row]:
    """Searches conversation history in the database."""
    rows = conn.execute(
        """SELECT rowid AS id, title, summary
            FROM conversations_fts
            WHERE conversations_fts MATCH ?
            LIMIT ?""",
        (query, limit),
    ).fetchall()
    return rows
