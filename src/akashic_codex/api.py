"""HTTP API: a second interface over the same core as the CLI.

Endpoints mirror the CLI commands (save / search / show) but speak JSON over
HTTP so any client can use the store. No storage or search logic lives here:
each endpoint translates the request, calls db / ingest / search, and returns
JSON (or raises an HTTPException). The schema is created once at startup.

Run with:  uvicorn akashic_codex.api:app --reload
       or:  python -m akashic_codex.cli serve
"""

import sqlite3
from collections.abc import Iterator
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Query
from pydantic import BaseModel

from akashic_codex import db
from akashic_codex.ingest import save_conversation
from akashic_codex.search import search


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Ensure the database schema exists before the server accepts requests."""
    db.init_db()
    yield


app = FastAPI(title="AkashicCodex", description="Local AI memory store", lifespan=lifespan)


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


@app.get("/conversations/{conv_id}", response_model=Conversation)
def get_conversation_endpoint(conv_id: int, conn: sqlite3.Connection = Depends(get_conn)):
    """Return one full conversation by id (tier-2 read), or 404 if it is missing."""
    row = db.get_conversation(conn, conv_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"No conversation with id {conv_id}")
    return Conversation(**dict(row))
