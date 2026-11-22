"""Forward-only schema migrations for existing SQLite stores."""

import sqlite3


def migration_1(conn: sqlite3.Connection) -> None:
    """Add summarizer provenance introduced after the original schema."""
    conn.execute("ALTER TABLE conversations ADD COLUMN summarizer TEXT")


def migration_2(conn: sqlite3.Connection) -> None:
    """Add Claude session upsert and cross-session thread identifiers."""
    conn.execute("ALTER TABLE conversations ADD COLUMN session_id TEXT")
    conn.execute("CREATE UNIQUE INDEX conversations_session_id ON conversations(session_id)")
    conn.execute("ALTER TABLE conversations ADD COLUMN thread_id TEXT")


def migration_3(conn: sqlite3.Connection) -> None:
    """Add locally generated, individually retrievable message summaries."""
    conn.execute(
        """CREATE TABLE message_chunks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            conversation_id INTEGER NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
            turn_index INTEGER NOT NULL,
            summary TEXT NOT NULL,
            content TEXT NOT NULL,
            UNIQUE (conversation_id, turn_index)
        )"""
    )


MIGRATIONS = (
    (1, migration_1),
    (2, migration_2),
    (3, migration_3),
)
