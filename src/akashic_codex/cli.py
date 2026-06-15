"""Command-line entry point. The fastest way to test the store as you build.

Planned usage:
    python -m akashic_codex.cli init
    python -m akashic_codex.cli save <file.txt> --title "..." --source claude
    python -m akashic_codex.cli search "what did I decide about the database?"
    python -m akashic_codex.cli show <id>
"""

import argparse


def main() -> None:
    parser = argparse.ArgumentParser(prog="akashic_codex", description="Local AI memory store")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("init", help="create the database")

    p_save = sub.add_parser("save", help="store a conversation from a text file")
    p_save.add_argument("file")
    p_save.add_argument("--title")
    p_save.add_argument("--source")

    p_search = sub.add_parser("search", help="search stored conversations")
    p_search.add_argument("query")
    p_search.add_argument("--limit", type=int, default=5)

    p_show = sub.add_parser("show", help="print a full conversation by id")
    p_show.add_argument("id", type=int)

    args = parser.parse_args()

    # TODO: wire each command to db / ingest / search functions.
    raise NotImplementedError(f"Command '{args.command}' not implemented yet")


if __name__ == "__main__":
    main()
