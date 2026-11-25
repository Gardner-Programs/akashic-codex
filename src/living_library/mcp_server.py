try:
    from mcp.server.fastmcp import FastMCP
except ModuleNotFoundError:
    from mcp.server.mcpserver import MCPServer as FastMCP

from .db import connect, get_default_db_path
from .search import search

DB_PATH = get_default_db_path()

mcp = FastMCP(
    name='living-library',
    instructions=(
        'Living Library stores your AI conversation history locally. Use search_memory to find '
        'relevant past conversations by keyword or semantic similarity, then use '
        'get_conversation to read a matching full transcript.'
    ),
)


@mcp.tool()
def search_memory(query: str, limit: int = 5) -> list[dict]:
    conn = connect(str(get_default_db_path()))
    return search(conn, query, limit)


@mcp.tool()
def get_conversation(conv_id: int) -> dict:
    conn = connect(str(get_default_db_path()))
    from .db import get_conversation

    row = get_conversation(conn, conv_id)
    if not row:
        raise ValueError(f'Conversation {conv_id} not found')
    return dict(row)


def run_mcp():
    mcp.run(transport='stdio')


if __name__ == '__main__':
    run_mcp()
