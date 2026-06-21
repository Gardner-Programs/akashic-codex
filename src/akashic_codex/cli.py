"""Command-line entry point. The fastest way to test the store as you build.

Planned usage:
    python -m akashic_codex.cli init
    python -m akashic_codex.cli save <file.txt> --title "..." --source claude
    python -m akashic_codex.cli search "what did I decide about the database?"
    python -m akashic_codex.cli show <id>
"""

import argparse
import sys
from pathlib import Path

from akashic_codex import db
from akashic_codex.ingest import save_conversation
from akashic_codex.search import search


def cmd_init(args):
    """Create the database."""
    db.init_db()
    print("Database Initialized")


def cmd_save(args):
    """Store a conversation read from a file; print its new id."""
    conn = db.connect()
    full_log = Path(args.file).read_text(encoding="utf-8")
    title = args.title
    source = args.source
    conv_id = save_conversation(conn, full_log, title, source)
    print(f"Conversation saved ID: {conv_id}")


def cmd_show(args):
    """Print a full conversation by id, or exit nonzero if it does not exist."""
    conn = db.connect()
    row = db.get_conversation(conn, args.id)
    if row is None:
        print(f"No conversation with id {args.id}", file=sys.stderr)
        sys.exit(1)
    print(f"{row['title']}  (id {row['id']}, source: {row['source']}, {row['created_at']})")
    print(row["full_log"])


def cmd_search(args):
    """Search stored conversations and print the ranked matches."""
    conn = db.connect()
    results = search(conn, args.query, args.limit)
    if not results:
        print("No matches found")
        return
    for result in results:
        print(f"[{result['id']}] {result['title']}")
        print(f"{result['summary']}")


def main() -> None:
    parser = argparse.ArgumentParser(prog="akashic_codex", description="Local AI memory store")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("init", help="create the database").set_defaults(func=cmd_init)

    p_save = sub.add_parser("save", help="store a conversation from a text file")
    p_save.add_argument("file")
    p_save.add_argument("--title")
    p_save.add_argument("--source")
    p_save.set_defaults(func=cmd_save)

    p_search = sub.add_parser("search", help="search stored conversations")
    p_search.add_argument("query")
    p_search.add_argument("--limit", type=int, default=5)
    p_search.set_defaults(func=cmd_search)

    p_show = sub.add_parser("show", help="print a full conversation by id")
    p_show.add_argument("id", type=int)
    p_show.set_defaults(func=cmd_show)

    args = parser.parse_args()
    try:
        args.func(args)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
