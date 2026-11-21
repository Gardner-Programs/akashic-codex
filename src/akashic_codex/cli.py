"""Command-line entry point. The fastest way to test the store as you build.

Usage:
    python -m akashic_codex.cli init
    python -m akashic_codex.cli save <file.txt> --title "..." --source claude
    python -m akashic_codex.cli search "what did I decide about the database?"
    python -m akashic_codex.cli show <id>
    python -m akashic_codex.cli serve_api [--host ... --port ... --reload]
    python -m akashic_codex.cli serve_mcp
    python -m akashic_codex.cli claude-hook   (Claude Code Stop hook; reads stdin JSON)
    python -m akashic_codex.cli reembed [--yes]
    python -m akashic_codex.cli retitle [--all] [--yes]
"""

import argparse
import json
import sys
from pathlib import Path

from akashic_codex import db
from akashic_codex.adapters import claude_transcript_to_log
from akashic_codex.ingest import save_conversation, save_session
from akashic_codex.search import search


def cmd_init(args):
    """Create the database."""
    db.init_db()
    print("Database Initialized")


def cmd_serve_api(args):
    """Start the HTTP API server."""
    import uvicorn

    uvicorn.run("akashic_codex.api:app", host=args.host, port=args.port, reload=args.reload)


def cmd_serve_mcp(args):
    """Start the MCP server over stdio (normally launched by an MCP client)."""
    from akashic_codex.mcp_server import run_mcp

    run_mcp()


def cmd_save(args):
    """Store a conversation read from a file; print its new id."""
    conn = db.connect()
    full_log = Path(args.file).read_text(encoding="utf-8")
    title = args.title
    source = args.source
    conv_id = save_conversation(conn, full_log, title, source)
    print(f"Conversation saved ID: {conv_id}")


def cmd_claude_hook(args):
    """Auto-save entry point, invoked by a Claude Code Stop hook.

    Claude Code hands us its payload as JSON on stdin. We pull out the session
    id and the path to the session transcript, flatten that transcript (via the
    Claude adapter) into a single log, and upsert it via save_session, so a
    session that grows over many turns updates one row instead of duplicating.
    """
    raw = sys.stdin.read()
    data = json.loads(raw)
    session_id = data["session_id"]
    transcript_path = data["transcript_path"]
    full_log = claude_transcript_to_log(transcript_path)
    conn = db.connect()
    save_session(conn, session_id, full_log, source="claude-code")


def cmd_reembed(args):
    """Rebuild every vector with the active embedding model, after confirming."""
    from akashic_codex.reembed import plan_reembed, reembed_store

    conn = db.connect()
    plan = plan_reembed(conn)
    old = plan["old_model"] or "unstamped"
    if plan["old_dim"]:
        old += f" ({plan['old_dim']} dims)"
    print(f"Re-embed {plan['count']} conversations: {old} -> {plan['new_model']}")
    print(f"Estimated cost: ${plan['cost']:.2f} (local model)")
    print("A backup of the database is written first.")
    if not args.yes and input("Proceed? [y/N] ").strip().lower() != "y":
        print("Aborted")
        return
    result = reembed_store(conn)
    print(
        f"Re-embedded {result['count']} conversations with {result['model']} ({result['dim']} dims)"
    )


def cmd_retitle(args):
    """Regenerate titles with the active titler, after confirming."""
    from akashic_codex.titlers import TITLER, retitle_store

    conn = db.connect()
    scope = "every conversation" if args.all else "untitled conversations"
    print(f"Retitle {scope} with {TITLER}. A backup of the database is written first.")
    if not args.yes and input("Proceed? [y/N] ").strip().lower() != "y":
        print("Aborted")
        return
    result = retitle_store(conn, all_rows=args.all)
    print(f"Backup written to {result['backup']}")
    print(f"Retitled {result['count']} of {result['scanned']} conversations")


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

    p_hook = sub.add_parser(
        "claude-hook", help="auto-save from a Claude Code Stop hook (reads JSON on stdin)"
    )
    p_hook.set_defaults(func=cmd_claude_hook)

    p_reembed = sub.add_parser(
        "reembed", help="rebuild all vectors with the active embedding model"
    )
    p_reembed.add_argument("--yes", action="store_true", help="skip the confirmation prompt")
    p_reembed.set_defaults(func=cmd_reembed)

    p_retitle = sub.add_parser("retitle", help="regenerate titles with the active titler")
    p_retitle.add_argument("--all", action="store_true", help="retitle every conversation")
    p_retitle.add_argument("--yes", action="store_true", help="skip the confirmation prompt")
    p_retitle.set_defaults(func=cmd_retitle)

    p_search = sub.add_parser("search", help="search stored conversations")
    p_search.add_argument("query")
    p_search.add_argument("--limit", type=int, default=5)
    p_search.set_defaults(func=cmd_search)

    p_show = sub.add_parser("show", help="print a full conversation by id")
    p_show.add_argument("id", type=int)
    p_show.set_defaults(func=cmd_show)

    p_serve = sub.add_parser("serve_api", help="start the HTTP API server")
    p_serve.add_argument("--host", default="127.0.0.1")
    p_serve.add_argument("--port", type=int, default=8000)
    p_serve.add_argument("--reload", action="store_true", help="auto-restart on code change (dev)")
    p_serve.set_defaults(func=cmd_serve_api)

    p_serve_mcp = sub.add_parser("serve_mcp", help="start the MCP server")
    p_serve_mcp.set_defaults(func=cmd_serve_mcp)

    args = parser.parse_args()
    try:
        args.func(args)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
