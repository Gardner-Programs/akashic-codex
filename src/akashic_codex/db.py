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
    raise NotImplementedError


def init_db(db_path: str = DB_PATH) -> None:
    """Create the schema if it does not exist.

    TODO: read schema.sql and executescript() it against a fresh connection.
    """
    raise NotImplementedError
