"""MCP server: a third interface over the same core as the CLI and REST API.

Exposes the read side of the store as MCP tools so any MCP-capable model can
recall past conversations directly. Write access stays on the CLI and REST API
by design: over MCP a model can recall memory, not mutate it. No storage or
search logic lives here; each tool opens a connection, calls db / search, and
returns JSON-able data.

The tool docstrings below are the schema the model reads to decide when and how
to call each tool, so they are written for that audience.

Launch (normally done by the MCP client, not by hand):
    python -m akashic_codex.mcp_server
"""

from mcp.server.mcpserver import MCPServer

from akashic_codex import db
from akashic_codex.memory import build_context, get_message_chunk, search_chunks
from akashic_codex.search import search

mcp = MCPServer("AkashicCodex")


@mcp.tool()
def search_memory(query: str, limit: int = 5) -> list[dict]:
    """Search the user's stored past conversations and return the best matches.

    Use this to recall earlier conversations by topic or wording, including when
    the user phrases things differently than they did originally. Returns ranked
    lightweight rows (id, title, summary) only, cheapest first to scan; pass an
    id to get_conversation to read the full transcript of a promising match.
    """
    conn = db.connect()
    try:
        return search(conn, query, limit)
    finally:
        conn.close()


@mcp.tool()
def get_conversation(conv_id: int) -> dict:
    """Return one full stored conversation by its id, including the transcript.

    Call this after search_memory, with an id from its results, to read the
    complete record (id, title, summary, source, created_at, full_log). Raises
    an error if no conversation has that id.
    """
    conn = db.connect()
    try:
        row = db.get_conversation(conn, conv_id)
        if row is None:
            raise ValueError("No result by that id found.")
        return dict(row)
    finally:
        conn.close()


@mcp.tool()
def get_context(conv_id: int, recent_turns: int = 4) -> dict:
    """Build brief, recent turns, and pointers for older conversation details."""
    conn = db.connect()
    try:
        result = build_context(conn, conv_id, recent_turns)
        if result is None:
            raise ValueError("No result by that id found.")
        return result
    finally:
        conn.close()


@mcp.tool()
def search_messages(query: str, limit: int = 10) -> list[dict]:
    """Search per-turn summaries; use get_message to fetch a matching turn's full text."""
    conn = db.connect()
    try:
        return search_chunks(conn, query, limit)
    finally:
        conn.close()


@mcp.tool()
def get_message(message_id: int) -> dict:
    """Retrieve a full turn chunk by id returned from context or search_messages."""
    conn = db.connect()
    try:
        result = get_message_chunk(conn, message_id)
        if result is None:
            raise ValueError("No message by that id found.")
        return result
    finally:
        conn.close()


def run_mcp():
    """Ensure the schema exists, then serve the tools over stdio."""
    db.init_db()
    mcp.run()


if __name__ == "__main__":
    run_mcp()
