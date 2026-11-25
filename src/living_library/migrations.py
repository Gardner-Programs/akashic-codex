import sqlite3


def migration_1(conn: sqlite3.Connection) -> None:
    """Add summarizer column to conversations table."""
    conn.execute('ALTER TABLE conversations ADD COLUMN summarizer TEXT')


def migration_2(conn: sqlite3.Connection) -> None:
    """Add session_id and thread_id columns to conversations table."""
    conn.execute('ALTER TABLE conversations ADD COLUMN session_id TEXT UNIQUE')
    conn.execute('ALTER TABLE conversations ADD COLUMN thread_id TEXT')
    # Create index for session_id lookups
    conn.execute(
        'CREATE INDEX IF NOT EXISTS idx_conversations_session_id ON conversations(session_id)'
    )
    # Create index for thread_id lookups
    conn.execute(
        'CREATE INDEX IF NOT EXISTS idx_conversations_thread_id ON conversations(thread_id)'
    )
