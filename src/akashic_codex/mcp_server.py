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

from mcp.server.fastmcp import FastMCP

from akashic_codex import db
from akashic_codex.search import search

mcp = FastMCP("AkashicCodex")


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


def run_mcp():
    """Ensure the schema exists, then serve the tools over stdio."""
    db.init_db()
    mcp.run()


if __name__ == "__main__":
    run_mcp()
