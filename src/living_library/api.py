"""HTTP API: a second interface over the same core as the CLI.

Endpoints mirror the CLI commands (save / search / show) but speak JSON over
HTTP so any client can use the store. No storage or search logic lives here:
each endpoint translates the request, calls db / ingest / search, and returns
JSON (or raises an HTTPException). The schema is created once at startup.

Run with:  uvicorn living_library.api:app --reload
       or:  python -m living_library.cli serve_api
"""

import sqlite3
from collections.abc import Iterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from living_library import db
from living_library.context import build_context
from living_library.ingest import save_conversation
from living_library.search import search


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Ensure the database schema exists before the server accepts requests."""
    db.init_db()
    yield


app = FastAPI(title="Living Library", description="Local AI memory store", lifespan=lifespan)


@app.get("/ui", response_class=HTMLResponse, include_in_schema=False)
def store_ui():
    """Serve a small browser for recent conversations and hybrid search."""
    html = Path(__file__).with_name("store.html").read_text(encoding="utf-8")
    return HTMLResponse(html)


def get_conn() -> Iterator[sqlite3.Connection]:
    """Yield a fresh per-request SQLite connection, closed after the response.

    A server is long-running and serves requests across threads, so it cannot
    share one connection the way the CLI did (open once, then exit). FastAPI
    resolves this via Depends, injects the yielded connection into the endpoint,
    then runs the cleanup in the finally once the response is sent.
    """
    conn = db.connect()
    try:
        yield conn
    finally:
        conn.close()


class ConversationIn(BaseModel):
    full_log: str
    title: str | None = None
    source: str | None = None


class SavedConversation(BaseModel):
    id: int


class SearchResult(BaseModel):
    id: int
    title: str
    summary: str


class ConversationPreview(BaseModel):
    id: int
    title: str
    summary: str | None = None
    source: str | None = None
    created_at: str


class Conversation(BaseModel):
    id: int
    title: str
    summary: str | None = None
    source: str | None = None
    created_at: str
    full_log: str


@app.post("/conversations", response_model=SavedConversation, status_code=201)
def save_conversation_endpoint(
    payload: ConversationIn, conn: sqlite3.Connection = Depends(get_conn)
):
    """Store a conversation via the ingest pipeline and return its new id."""
    new_id = save_conversation(conn, payload.full_log, payload.title, payload.source)
    return SavedConversation(id=new_id)


@app.get("/search", response_model=list[SearchResult])
def search_conversation_endpoint(
    query: str = Query(min_length=1, description="search text"),
    limit: int = 5,
    conn: sqlite3.Connection = Depends(get_conn),
):
    """Hybrid search over stored conversations; return ranked lightweight rows."""
    rows = search(conn, query, limit)
    return rows


@app.get("/conversations", response_model=list[ConversationPreview])
def list_conversations_endpoint(
    limit: int = Query(default=20, ge=1, le=100), conn: sqlite3.Connection = Depends(get_conn)
):
    """List recent lightweight conversation rows for browsing."""
    return [ConversationPreview(**dict(row)) for row in db.list_conversations(conn, limit)]


@app.get("/conversations/{conv_id}", response_model=Conversation)
def get_conversation_endpoint(conv_id: int, conn: sqlite3.Connection = Depends(get_conn)):
    """Return one full conversation by id (tier-2 read), or 404 if it is missing."""
    row = db.get_conversation(conn, conv_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"No conversation with id {conv_id}")
    return Conversation(**dict(row))


@app.get("/messages/{message_id}")
def get_message_endpoint(message_id: int, conn: sqlite3.Connection = Depends(get_conn)):
    """Return one full turn chunk by id."""
    row = db.get_message_chunk(conn, message_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"No message with id {message_id}")
    return dict(row)


@app.get("/conversations/{conv_id}/context")
def conversation_context_endpoint(
    conv_id: int,
    recent_turns: int = Query(default=6, ge=0, le=100),
    conn: sqlite3.Connection = Depends(get_conn),
):
    """Build a compact brief plus a bounded window of full recent turns."""
    result = build_context(conn, conv_id, recent_turns)
    if result is None:
        raise HTTPException(status_code=404, detail=f"No conversation with id {conv_id}")
    return result
